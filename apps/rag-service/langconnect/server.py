import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from idempotency import AsyncRedisPool, IdempotencyConfig, IdempotencyMiddleware

from langconnect.api import (
    collections_router,
    datasources_router,
    documents_router,
    graph_router,
)
from langconnect.config import (
    ALLOWED_ORIGINS,
    IDEMPOTENCY_ENABLED,
    IDEMPOTENCY_TTL,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
)
from langconnect.database.collections import CollectionsManager
from langconnect.database.postgres.schema_bootstrap import ensure_schema

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# Initialize FastAPI app


_idempotency_config = IdempotencyConfig(
    redis_host=REDIS_HOST,
    redis_port=REDIS_PORT,
    redis_db=REDIS_DB,
    redis_password=REDIS_PASSWORD,
    idempotency_ttl=IDEMPOTENCY_TTL,
    idempotency_enabled=IDEMPOTENCY_ENABLED,
    service_name="rag-service",
)


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


APP = FastAPI(
    title="LangConnect API",
    description="A REST API for a RAG system using FastAPI and LangChain",
    version="0.1.0",
    lifespan=lifespan,
)

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
    exclude_paths={"/health", "/api/health"},
)

# Include API routers
APP.include_router(collections_router)
APP.include_router(datasources_router)
APP.include_router(documents_router)
APP.include_router(graph_router)


@APP.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
