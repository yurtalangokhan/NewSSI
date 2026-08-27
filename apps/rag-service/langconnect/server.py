import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from langconnect.config import ALLOWED_ORIGINS
from langconnect.database.postgres.schema_bootstrap import ensure_schema
from langconnect.idempotency import (
    build_idempotency_config,
    build_idempotency_exclude_paths,
)
from langconnect.services.collections import CollectionsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# Initialize FastAPI app


_idempotency_config = build_idempotency_config()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI application."""
    logger.info("App is starting up. Creating background worker...")
    await AsyncRedisPool.connect(_idempotency_config)
    await ensure_schema()
    await CollectionsManager.setup()

    # Initialize Neo4j connection (best-effort - graph features degrade gracefully)
    try:
        from langconnect.database.neo4j.connection import get_neo4j_driver

        await get_neo4j_driver()
        logger.info("Neo4j connection established.")
    except Exception:
        logger.warning("Neo4j is not available - graph features will be disabled.")

    yield

    await AsyncRedisPool.close()

    # Shutdown
    try:
        from langconnect.database.neo4j.connection import close_neo4j_driver

        await close_neo4j_driver()
    except Exception:
        logger.warning("Failed to close Neo4j driver.", exc_info=True)

    try:
        from langconnect.database.postgres.engine import close_db_engine

        await close_db_engine()
    except Exception:
        logger.warning("Failed to close Postgres engine.", exc_info=True)

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
