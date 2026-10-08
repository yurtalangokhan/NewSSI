"""
FastAPI application factory.

Creates the ``app`` instance, registers lifespan, CORS middleware,
the health-check endpoint, and includes every sub-router.

This is the *only* module that needs to know about all route modules.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
import warnings

from config_manager import env
from error_contract import ERROR_RESPONSES, apply_idempotency_openapi, register_error_handlers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from idempotency import AsyncRedisPool
from langchain_core._api import LangChainBetaWarning
from langfuse import Langfuse
from localization import LocalizationMiddleware, init_localization
from metrics import MetricsMiddleware, metrics_endpoint
from observability import CorrelationMiddleware
from security import assert_gateway_routed, close_all as security_close_all, validate_cors_policy

from agents import get_agent, get_all_agent_info, load_agent
from core.http.api_versioning import API_PREFIX
from core.http.idempotency import (
    AgentResponseIdempotencyMiddleware,
    build_idempotency_config,
    build_idempotency_exclude_paths,
)
from core.http.response_errors import register_response_errors
from core.observability.observability import (
    DependencyPolicy,
    configure_logging,
    configure_telemetry,
    dependency_registry,
    get_logger,
    readiness_payload,
    retry_async,
)
from core.security.mcp.mcp_url_policy import default_mcp_url
from infrastructure.db import close_db_engine, get_db_engine
from infrastructure.db.startup import run_startup_migrations
from infrastructure.runtime.chat_runs.wiring import new_instance_id, start_chat_runs, stop_chat_runs
from infrastructure.runtime.checkpointer import set_global_checkpointer
from infrastructure.runtime.langgraph_store import set_global_langgraph_store
from memory import initialize_database, initialize_store
from memory.postgres import close_shared_pool
from schemas.common import HealthCheckResponse, ReadinessResponse
from service.chat_runs.settings import ChatRunSettings
from service.ingest.connector_runtime import get_connector_runtime
from service.mcp.mcp_provider_service import MCPProviderService
from service.runtime.playground_retention_service import get_playground_retention_worker

_idempotency_config = build_idempotency_config(env)

warnings.filterwarnings("ignore", category=LangChainBetaWarning)
configure_logging(
    service_name="agent-service",
    log_level=env.agent_log_level,
    log_format=env.LOG_FORMAT,
)
configure_telemetry()
logger = get_logger(__name__)


# =============================================================================
# Helpers
# =============================================================================


_colliding_operation_names: set[str] | None = None


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate idiomatic, unique operation IDs for OpenAPI client generation.

    Preserves plain function names for unique routes, and disambiguates colliding
    route names across routers using their tags.
    """
    global _colliding_operation_names
    if _colliding_operation_names is None:
        from collections import Counter

        counts = Counter(r.name for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema)
        _colliding_operation_names = {name for name, count in counts.items() if count > 1}

    if route.name in _colliding_operation_names:
        tag = str(route.tags[0]) if route.tags else "default"
        clean_tag = tag.replace("-", "_").replace(" ", "_")
        return f"{clean_tag}_{route.name}"
    return route.name


# =============================================================================
# Lifespan
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Configurable lifespan that initializes the appropriate database checkpointer,
    store, and agents with async loading.
    """
    # Fail fast on a service URL that would bypass Gateway. Services no longer
    # authenticate callers, so such a URL yields 401 on every call at runtime.
    assert_gateway_routed(
        {
            "INTERNAL_USER_SERVICE_URL": env.INTERNAL_USER_SERVICE_URL,
            "INTERNAL_TOOLS_SERVICE_URL": env.INTERNAL_TOOLS_SERVICE_URL,
        }
    )
    assert_gateway_routed(
        {
            "INTERNAL_RAG_SERVICE_API_URL": env.INTERNAL_RAG_SERVICE_API_URL,
        },
        required=False,
    )

    try:
        run_startup_migrations()
        _sa_engine = get_db_engine()
        dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
        logger.info("SQLAlchemy async engine ready: %s", _sa_engine.url.database)

        async with (
            initialize_database() as saver,
            initialize_store() as langgraph_store,
        ):
            logger.info(f"LangGraph store initialized: {type(langgraph_store).__name__}")

            agents = get_all_agent_info()
            for a in agents:
                try:
                    await load_agent(a.key)
                    logger.info(f"Agent loaded: {a.key}")
                except Exception as e:
                    logger.error(f"Failed to load agent {a.key}: {e}")

                agent = get_agent(a.key)
                agent.checkpointer = saver
                logger.info(
                    f"[APP STARTUP] Set checkpointer on agent '{a.key}': {type(agent)}, has_checkpointer={agent.checkpointer is not None}"
                )
                agent.store = langgraph_store

            set_global_checkpointer(saver)
            set_global_langgraph_store(langgraph_store)

            mcp_service = MCPProviderService.get_instance()
            try:
                mcp_url = default_mcp_url()
                await mcp_service.initialize_builtin(mcp_url)
                dependency_registry.record_ok("tools-service", policy=DependencyPolicy.DEGRADED)
                logger.info(f"MCP Provider initialized: {mcp_url}")
            except Exception:
                dependency_registry.record_degraded(
                    "tools-service",
                    hint="Tool execution is unavailable until tools-service is reachable.",
                )
                logger.warning(
                    "tools-service is unavailable; tool execution will be degraded.",
                    extra={
                        "event": "startup.dependency.degraded",
                        "dependency": "tools-service",
                        "operation": "initialize_builtin",
                        "status": "degraded",
                    },
                )

            connector_runtime = get_connector_runtime()
            try:
                await connector_runtime.start()
            except Exception:
                # Schedules and resumed syncs wait for the next restart; the
                # datasource API itself does not need the background loop.
                logger.exception("Connector runtime failed to start; scheduled syncs are off.")

            retention_worker = get_playground_retention_worker()
            retention_worker.start()

            redis_client = await retry_async(
                lambda: AsyncRedisPool.connect(_idempotency_config),
                operation_name="connect",
                dependency="redis",
            )
            dependency_registry.record_ok("redis", policy=DependencyPolicy.REQUIRED)
            logger.info(
                "Redis idempotency pool connected.",
                extra={
                    "event": "startup.dependency.ok",
                    "dependency": "redis",
                    "operation": "connect",
                    "status": "ok",
                },
            )

            chat_runs = start_chat_runs(
                redis_client,
                settings=ChatRunSettings.from_env(env),
                instance_id=new_instance_id(),
            )

            yield

            await stop_chat_runs(chat_runs)
            await AsyncRedisPool.close()
            await retention_worker.stop()
            await connector_runtime.stop()
            await security_close_all()

            from infrastructure.diagrams import close_diagram_renderer

            await close_diagram_renderer()

            from memory.long_term import cancel_all_background_tasks

            await cancel_all_background_tasks()

        await close_db_engine()
        await close_shared_pool()

    except Exception as e:
        logger.error(f"Error during database/store/agents initialization: {e}")
        raise


# =============================================================================
# App instance
# =============================================================================

# In local dev app.py lives under src/, one level below the service root that
# holds locales/. In the Docker image the file is flattened directly into the
# app root instead, so fall back to a locales/ dir next to the file itself.
_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_localization(locales_dir)

app = FastAPI(
    title="Agent Service API",
    description=(
        "LangGraph multi-agent orchestration: agent and flow definitions, "
        "threaded conversations, streaming runs, and tool execution."
    ),
    version="1.0.0",
    responses=ERROR_RESPONSES,
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
)

register_error_handlers(app, service_name="agent-service")
# Idempotency declarations first: the response-error registration then rewrites
# every 4xx/5xx body to this service's own error schema, so the middleware's
# statuses are documented with the envelope actually sent.
apply_idempotency_openapi(app)
register_response_errors(app)

app.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

app.add_middleware(LocalizationMiddleware)

CORS_ORIGINS = [o.strip() for o in env.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
# Fails startup rather than serving a CORS policy that grants no
# protection at all: allow_origins=["*"] with allow_credentials=True makes
# the browser reflect any requesting Origin and send cookies with it.
validate_cors_policy(origins=CORS_ORIGINS, allow_credentials=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Location"],
)


app.add_middleware(
    AgentResponseIdempotencyMiddleware,
    config=_idempotency_config,
    exclude_paths=build_idempotency_exclude_paths(API_PREFIX),
)

# Just inside metrics, so every record written while handling a request - by
# handlers, idempotency, CORS, or the error handlers - carries the same
# correlation id, while metrics stays outermost and keeps counting the
# responses idempotency short-circuits.
app.add_middleware(CorrelationMiddleware)


# Registered last, so it is outermost: the counters must observe the responses
# the idempotency middleware short-circuits, such as a 503 from an unavailable
# store. Metrics writes no log records, so it needs no correlation id itself.
app.add_middleware(MetricsMiddleware, service_name="agent-service")


# =============================================================================
# Health check (on app, not router — no auth required)
# =============================================================================


async def _health_status():
    """Build the agent-service health response."""
    health_status = {"status": "ok"}

    if env.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status


@app.get(f"{API_PREFIX}/health", response_model=HealthCheckResponse)
async def api_health_check():
    """Versioned health check endpoint."""
    return await _health_status()


@app.get(f"{API_PREFIX}/health/ready", response_model=ReadinessResponse)
async def api_readiness_check():
    """Readiness endpoint reporting dependency state."""
    payload = readiness_payload(service_name="agent-service")
    if payload["status"] != "ready":
        return JSONResponse(status_code=503, content=payload)
    return payload


# =============================================================================
# Include routers (centralized modular registration)
# =============================================================================

from api.router import register_api_routes  # noqa: E402

register_api_routes(app)

if __name__ == "__main__":
    import asyncio
    import sys

    import uvicorn

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run(
        "app:app",
        host=env.HOST,
        port=env.AGENT_SERVICE_PORT,
        reload=env.is_dev(),
        timeout_graceful_shutdown=env.GRACEFUL_SHUTDOWN_TIMEOUT,
    )
