from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from i18n import I18nMiddleware, init_service_i18n
from idempotency import AsyncRedisPool, IdempotencyMiddleware

from langconnect.api import (
    collections_router,
    datasources_router,
    documents_router,
    graph_router,
    retrieval_router,
)
from langconnect.api_versioning import API_PREFIX
from langconnect.config import ALLOWED_ORIGINS, LOG_FORMAT, LOG_LEVEL
from langconnect.database.postgres.schema_bootstrap import ensure_schema
from langconnect.idempotency import (
    build_idempotency_config,
    build_idempotency_exclude_paths,
)
from langconnect.observability import (
    DependencyPolicy,
    configure_logging,
    dependency_error_fields,
    dependency_registry,
    get_logger,
    readiness_payload,
    retry_async,
)
from langconnect.services.collections import CollectionsManager

configure_logging(
    service_name="rag-service",
    log_level=LOG_LEVEL,
    log_format=LOG_FORMAT,
)
logger = get_logger(__name__)


# Initialize FastAPI app


_idempotency_config = build_idempotency_config()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI application."""
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
    await retry_async(
        ensure_schema,
        operation_name="bootstrap_schema",
        dependency="postgres",
    )
    dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    await CollectionsManager.setup()

    # Initialize Neo4j connection (best-effort - graph features degrade gracefully)
    try:
        from langconnect.database.neo4j.connection import get_neo4j_driver

        await get_neo4j_driver()
        dependency_registry.record_ok("neo4j", policy=DependencyPolicy.DEGRADED)
        logger.info("Neo4j connection established.")
    except Exception as exc:
        dependency_registry.record_degraded(
            "neo4j", hint="Graph features are disabled until Neo4j is reachable."
        )
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
        from langconnect.database.neo4j.connection import close_neo4j_driver

        await close_neo4j_driver()
    except Exception as exc:
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
        from langconnect.database.postgres.engine import close_db_engine

        await close_db_engine()
    except Exception as exc:
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

    logger.info("App is shutting down. Stopping background worker...")


_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_service_i18n(locales_dir)

APP = FastAPI(
    title="LangConnect API",
    description="A REST API for a RAG system using FastAPI and LangChain",
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(APP, service_name="rag-service")

APP.add_middleware(I18nMiddleware)

# Add CORS middleware
APP.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


APP.add_middleware(
    IdempotencyMiddleware,
    config=_idempotency_config,
    exclude_paths=build_idempotency_exclude_paths(API_PREFIX),
)

# Include API routers
APP.include_router(collections_router, prefix=API_PREFIX)
APP.include_router(datasources_router, prefix=API_PREFIX)
APP.include_router(documents_router, prefix=API_PREFIX)
APP.include_router(graph_router, prefix=API_PREFIX)
APP.include_router(retrieval_router, prefix=API_PREFIX)


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

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
