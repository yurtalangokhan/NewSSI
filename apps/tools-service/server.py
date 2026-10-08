"""
MCP Server with HTTP transport for Open Agent Platform.
Uses FastMCP with custom routes for OpenAPI, Swagger UI, Prometheus metrics,
governance, health, readiness, and security compliance.
"""

import contextlib
from pathlib import Path
import sys

from config_manager import load_environment

# Load the shared configuration before importing service components
load_environment()

# The service package itself is imported as `src.*` relative to this file.
sys.path.insert(0, str(Path(__file__).parent))

# Suppress WinError 10054 on Windows
if sys.platform == "win32":
    import asyncio.proactor_events as _pe

    _orig_call_connection_lost = _pe._ProactorBasePipeTransport._call_connection_lost

    def _patched_call_connection_lost(self, exc):
        with contextlib.suppress(ConnectionResetError, OSError):
            _orig_call_connection_lost(self, exc)

    _pe._ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost

from config_manager import env
from error_contract import (
    ERROR_RESPONSES,
    apply_idempotency_openapi,
    error_responses,
    register_error_handlers,
)
from fastapi import APIRouter, FastAPI, Response
from fastmcp import FastMCP
from idempotency import IdempotencyMiddleware
from localization import LocalizationMiddleware, init_localization
from metrics import MetricsMiddleware, metrics_endpoint
from observability import CorrelationMiddleware
from pydantic import BaseModel, Field
from security import assert_gateway_routed
from starlette.middleware import Middleware
from starlette.routing import Match, Route

from src.core.auth import GatewayTokenVerifier
from src.core.database import close_db_pool
from src.core.idempotency import build_idempotency_config, build_idempotency_exclude_paths
from src.core.observability import (
    DependencyPolicy,
    configure_logging,
    configure_telemetry,
    dependency_registry,
    get_logger,
    readiness_payload,
)
from src.core.registry import ToolRegistry
from src.core.trusted_middleware import TrustedContextMiddleware
from src.models.response_errors import register_response_errors

locales_dir = Path(__file__).parent / "locales"
init_localization(locales_dir)
configure_logging(service_name="tools-service", log_level=env.LOG_LEVEL)
configure_telemetry()
logger = get_logger(__name__)

# Fail fast on a service URL that would bypass Gateway. Services no longer
# authenticate callers, so such a URL yields 401 on every call at runtime.
_settings = env
_settings.validate_tools_service()
assert_gateway_routed({"USER_SERVICE_URL": _settings.INTERNAL_USER_SERVICE_URL})
assert_gateway_routed(
    {
        "AGENT_SERVICE_URL": _settings.INTERNAL_AGENT_SERVICE_URL,
        "RAG_SERVICE_API_URL": _settings.INTERNAL_RAG_SERVICE_API_URL,
    },
    required=False,
)

# Initialize FastMCP server
mcp = FastMCP("open-agent-tools", auth=GatewayTokenVerifier())


class HealthStatus(BaseModel):
    """Liveness response."""

    status: str = Field(examples=["ok"])


class DependencyStatus(BaseModel):
    """State of one downstream dependency."""

    status: str = Field(examples=["ready"])
    required: bool
    hint: str | None = None


class ReadinessStatus(BaseModel):
    """Readiness response, including per-dependency detail."""

    status: str = Field(examples=["ready", "not_ready"])
    service: str | None = None
    dependencies: dict[str, DependencyStatus] = Field(default_factory=dict)


router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness check", operation_id="tools_health_check")
async def health_check() -> HealthStatus:
    """Report that the process is up and serving HTTP."""
    return HealthStatus(status="ok")


@router.get(
    "/health/ready",
    summary="Readiness check",
    operation_id="tools_readiness_check",
    responses=error_responses(503),
)
async def readiness_check(response: Response) -> ReadinessStatus:
    """Report whether every required dependency is reachable."""
    payload = readiness_payload(service_name="tools-service")
    if payload["status"] != "ready":
        response.status_code = 503
    return ReadinessStatus.model_validate(payload)


# Initialize the tool registry with plugin discovery
registry = ToolRegistry(mcp)
plugins_dir = Path(__file__).parent / "src" / "tools"
registry.discover_plugins(str(plugins_dir))


async def record_startup_dependencies() -> None:
    """Fill in the readiness registry.

    Nothing used to record anything here, so /ready answered "ready" over an
    empty dependency map — a green light that had checked nothing.
    """
    categories = registry.list_categories()
    if categories:
        dependency_registry.record_ok("tool-registry", policy=DependencyPolicy.REQUIRED)
    else:
        dependency_registry.record_degraded("tool-registry", hint="no tool categories loaded")

    config = build_idempotency_config(env)
    if config.idempotency_enabled:
        try:
            from idempotency.redis_client import AsyncRedisPool

            await (await AsyncRedisPool.connect(config)).ping()
            # DEGRADED, not REQUIRED: idempotency caching going down should
            # not take the whole service out of rotation.
            dependency_registry.record_ok("redis", policy=DependencyPolicy.DEGRADED)
        except Exception as exc:
            dependency_registry.record_degraded("redis", hint=str(exc)[:200])


async def cleanup():
    """Cleanup resources on shutdown."""
    await registry.cleanup_all()
    await close_db_pool()

    from src.tools.web_tools import get_http_client

    await get_http_client().aclose()

    # The idempotency middleware keeps its own Redis pool; nothing closed it,
    # so every reload leaked the connections it held.
    try:
        from idempotency.redis_client import AsyncRedisPool

        await AsyncRedisPool.close()
    except Exception:
        logger.warning("Failed to close the idempotency Redis pool", exc_info=True)


#: Documents the token the MCP transport requires. tools-service authenticates
#: through FastMCP's ``KeycloakTokenVerifier`` rather than a FastAPI dependency,
#: so the scheme is declared explicitly instead of being inferred from routes.
KEYCLOAK_SECURITY_SCHEME = {
    "KeycloakBearer": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Keycloak-issued access token, verified by KeycloakTokenVerifier.",
    }
}


def build_service_middleware() -> list[Middleware]:
    """Build the middleware applied to the embedded MCP transport.

    Metrics are deliberately absent here: the FastAPI application already wraps
    the transport with ``MetricsMiddleware``, and a second instance on the
    inner app would count every MCP request twice.
    """
    settings = env
    return [
        Middleware(LocalizationMiddleware),
        Middleware(
            IdempotencyMiddleware,
            config=build_idempotency_config(settings),
            exclude_paths=build_idempotency_exclude_paths(),
        ),
        Middleware(TrustedContextMiddleware),
    ]


class _AsgiRoute(Route):
    """A Starlette route for a raw ASGI app that publishes itself in the scope.

    FastAPI's ``APIRoute`` stores the matched route in ``scope["route"]`` and
    the shared ``MetricsMiddleware`` labels requests from it. A plain Starlette
    ``Route`` does not, which would file every MCP request under
    ``__unmatched__``. This mirrors ``APIRoute`` for the one route that cannot
    be a FastAPI endpoint because it hands the connection to a sub-application.
    """

    def matches(self, scope: dict) -> tuple[Match, dict]:
        match, child_scope = super().matches(scope)
        if match is not Match.NONE:
            child_scope["route"] = self
        return match, child_scope


def _document_mcp_transport(app: FastAPI) -> None:
    """Describe the embedded MCP sub-application in the OpenAPI document.

    Everything else in the document is generated from FastAPI routes. The MCP
    transport is an embedded ASGI application speaking JSON-RPC, which FastAPI
    cannot introspect, so this one path is declared by hand — deliberately, and
    in one place.
    """
    generate = app.openapi

    def openapi_with_mcp() -> dict:
        schema = generate()
        schema["paths"].setdefault(
            "/mcp",
            {
                "post": {
                    "tags": ["mcp"],
                    "summary": "MCP streamable HTTP transport (JSON-RPC 2.0)",
                    "operationId": "mcp_transport",
                    "security": [{"KeycloakBearer": []}],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {
                        "200": {
                            "description": "JSON-RPC response, or an SSE stream of them",
                            "content": {"text/event-stream": {"schema": {"type": "string"}}},
                        },
                        **{
                            str(code): {
                                "description": spec["description"],
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                                    }
                                },
                            }
                            for code, spec in error_responses(401, 403, 500).items()
                        },
                    },
                }
            },
        )
        return schema

    app.openapi = openapi_with_mcp


def build_http_app() -> FastAPI:
    """Build the tools-service FastAPI application with the MCP transport embedded in it.

    The MCP transport keeps its own session manager, which lives in the sub
    application's lifespan; that lifespan is chained into the parent so embedding
    does not silently leave the manager unstarted.

    Call this once per process: the session manager belongs to the module-level
    ``mcp`` instance and refuses to start twice.
    """
    mcp_app = mcp.http_app(
        path="/mcp",
        transport="http",
        middleware=build_service_middleware(),
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_app.lifespan(app):
            await record_startup_dependencies()
            try:
                yield
            finally:
                await cleanup()

    app = FastAPI(
        title="Tools Service API",
        description=(
            "Tool execution service exposing mathematical, system, text and "
            "connector operations over the Model Context Protocol."
        ),
        version="1.0.0",
        responses=ERROR_RESPONSES,
        lifespan=lifespan,
    )

    register_error_handlers(
        app,
        service_name="tools-service",
        security_schemes=KEYCLOAK_SECURITY_SCHEME,
    )
    # Before _document_mcp_transport: the hand-written /mcp operation describes
    # errors produced by the embedded transport, which this envelope does not cover.
    register_response_errors(app)
    app.include_router(router)
    app.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
    # Streamable HTTP is a single endpoint, so the sub-app is attached as an
    # exact route rather than a mount. A mount at "/mcp" only matches "/mcp/…"
    # and Starlette answers a bare "POST /mcp" with a 307 that MCP clients do
    # not follow; a mount at "/" would swallow every unknown path and bypass
    # the error contract's 404 envelope.
    app.router.routes.append(
        _AsgiRoute(
            "/mcp", endpoint=mcp_app, methods=["GET", "POST", "DELETE"], include_in_schema=False
        )
    )
    _document_mcp_transport(app)
    # After _document_mcp_transport: that helper replaces app.openapi with its
    # own wrapper, so the idempotency patch must wrap the final callable to
    # reach the hand-built /mcp operation.
    apply_idempotency_openapi(app)
    app.add_middleware(CorrelationMiddleware)

    # Registered last, so it is outermost: the counters must observe the
    # responses the idempotency middleware short-circuits, such as a 503 from
    # an unavailable store. Metrics writes no log records, so it needs no
    # correlation id itself.
    app.add_middleware(MetricsMiddleware, service_name="tools-service")
    return app


def log_startup_banner(*, host: str, port: int, logger) -> None:
    """Log the HTTP server startup details with structured fields."""
    logger.info(
        "Starting FastMCP Server.",
        extra={
            "event": "startup.server.starting",
            "dependency": None,
            "operation": "serve_http",
            "status": "starting",
            "host": host,
            "port": port,
            "mcp_endpoint": f"http://{host}:{port}/mcp",
        },
    )


#: Module-level ASGI application, so the service can be served the same way as
#: every other one: ``uvicorn server:app``.
app = build_http_app()


if __name__ == "__main__":
    import uvicorn

    settings = env
    host, port = settings.MCP_HOST, settings.TOOLS_SERVICE_PORT

    log_startup_banner(host=host, port=port, logger=logger)
    uvicorn.run(app, host=host, port=port)
