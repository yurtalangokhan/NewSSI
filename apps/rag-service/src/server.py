# Copyright (c) 2026 Agentic AI Platform
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from config_manager import env, parse_allowed_origins
from error_contract import (
    ERROR_RESPONSES,
    apply_idempotency_openapi,
    register_error_handlers,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from idempotency import AsyncRedisPool
from localization import LocalizationMiddleware, init_localization
from metrics import MetricsMiddleware, metrics_endpoint
from observability import CorrelationMiddleware
from security import validate_cors_policy

from src.collections.router import router as collections_router
from src.collections.service import CollectionsManager
from src.datasources.router import router as datasources_router
from src.documents.router import router as documents_router
from src.graph.router import router as graph_router
from src.memory.router import router as memory_router
from src.retrieval.router import router as retrieval_router
from src.search.router import router as search_router
from src.shared.api_versioning import API_PREFIX
from src.shared.gateway_routing import assert_gateway_routed
from src.shared.idempotency import (
    RagResponseIdempotencyMiddleware,
    build_idempotency_config,
    build_idempotency_exclude_paths,
)
from src.shared.observability import (
    DependencyPolicy,
    configure_logging,
    configure_telemetry,
    dependency_error_fields,
    dependency_registry,
    get_logger,
    readiness_payload,
    retry_async,
)
from src.shared.postgres.startup import run_startup_migrations
from src.shared.response_errors import register_response_errors

configure_logging(
    service_name="rag-service",
    log_level=env.LOG_LEVEL,
    log_format=env.LOG_FORMAT,
)
configure_telemetry()
logger = get_logger(__name__)


# Initialize FastAPI app


_idempotency_config = build_idempotency_config()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI application."""
    # Fail fast on a service URL that would bypass Gateway.
    assert_gateway_routed({"USER_SERVICE_URL": env.INTERNAL_USER_SERVICE_URL})

    run_startup_migrations()
    dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    logger.info("App is starting up. Creating background worker...")
    await retry_async(
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
    await CollectionsManager.setup()

    # Initialize Neo4j connection (best-effort - graph features degrade gracefully)
    try:
        from src.graph.connection import (
            get_neo4j_driver,
        )

        await get_neo4j_driver()
        dependency_registry.record_ok("neo4j", policy=DependencyPolicy.DEGRADED)
        logger.info("Neo4j connection established.")
    except Exception as exc:  # Lifecycle boundary records optional startup/cleanup failures.
        dependency_registry.record_degraded("neo4j", hint="Graph features are disabled until Neo4j is reachable.")
        logger.warning(
            "Neo4j is not available - graph features will be disabled.",
            extra={
                **dependency_error_fields(exc, dependency="neo4j"),
                "event": "startup.dependency.degraded",
                "dependency": "neo4j",
                "operation": "connect",
                "status": "degraded",
            },
        )

    yield

    await AsyncRedisPool.close()

    # Shutdown
    try:
        from src.graph.connection import (
            close_neo4j_driver,
        )

        await close_neo4j_driver()
    except Exception as exc:  # Lifecycle boundary records optional startup/cleanup failures.
        logger.warning(
            "neo4j shutdown cleanup failed.",
            extra={
                **dependency_error_fields(exc, dependency="neo4j"),
                "event": "shutdown.dependency.cleanup_failed",
                "dependency": "neo4j",
                "operation": "close_driver",
                "status": "degraded",
            },
        )

    try:
        from src.shared.postgres.engine import (
            close_db_engine,
        )

        await close_db_engine()
    except Exception as exc:  # Lifecycle boundary records optional startup/cleanup failures.
        logger.warning(
            "postgres shutdown cleanup failed.",
            extra={
                **dependency_error_fields(exc, dependency="postgres"),
                "event": "shutdown.dependency.cleanup_failed",
                "dependency": "postgres",
                "operation": "close_engine",
                "status": "degraded",
            },
        )

    from security import (
        close_all as security_close_all,
    )

    await security_close_all()

    from src.graph.service import (
        cancel_all_background_tasks,
    )

    await cancel_all_background_tasks()

    logger.info("App is shutting down. Stopping background worker...")


_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_localization(locales_dir)

APP = FastAPI(
    title="RAG Service API",
    description="A REST API for a RAG system using FastAPI and LangChain",
    version="1.0.0",
    responses=ERROR_RESPONSES,
    lifespan=lifespan,
)

register_error_handlers(APP, service_name="rag-service")
register_response_errors(APP)
apply_idempotency_openapi(APP)

APP.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

APP.add_middleware(LocalizationMiddleware)

# Fails startup rather than serving a CORS policy that grants no
# protection at all: allow_origins=["*"] with allow_credentials=True makes
# the browser reflect any requesting Origin and send cookies with it.
validate_cors_policy(origins=parse_allowed_origins(env.ALLOW_ORIGINS), allow_credentials=True)

APP.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(env.ALLOW_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


APP.add_middleware(
    RagResponseIdempotencyMiddleware,
    config=_idempotency_config,
    exclude_paths=build_idempotency_exclude_paths(API_PREFIX),
)

APP.add_middleware(CorrelationMiddleware)

# Registered last, so it is outermost: the counters must observe the responses
# the idempotency middleware short-circuits, such as a 503 from an unavailable
# store. Metrics writes no log records, so it needs no correlation id itself.
APP.add_middleware(MetricsMiddleware, service_name="rag-service")

# Include API routers
APP.include_router(collections_router, prefix=API_PREFIX)
APP.include_router(datasources_router, prefix=API_PREFIX)
APP.include_router(documents_router, prefix=API_PREFIX)
APP.include_router(graph_router, prefix=API_PREFIX)
APP.include_router(memory_router, prefix=API_PREFIX)
APP.include_router(retrieval_router, prefix=API_PREFIX)
APP.include_router(search_router, prefix=API_PREFIX)


@APP.get(f"{API_PREFIX}/health")
async def api_health_check() -> dict:
    """Versioned health check endpoint."""
    return {"status": "ok"}


@APP.get(f"{API_PREFIX}/health/ready")
async def api_readiness_check() -> JSONResponse:
    """Readiness endpoint reporting dependency state."""
    payload = readiness_payload(service_name="rag-service")
    if payload["status"] != "ready":
        return JSONResponse(status_code=503, content=payload)
    return JSONResponse(content=payload)


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 is required inside the container; APISIX is the only ingress.
    uvicorn.run("src.server:APP", host="0.0.0.0", port=env.RAG_SERVICE_PORT, reload=True)  # noqa: S104
