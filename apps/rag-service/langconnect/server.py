import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langconnect.api import collections_router, documents_router, graph_router
from langconnect.config import ALLOWED_ORIGINS
from langconnect.database.collections import CollectionsManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# Initialize FastAPI app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI application."""
    logger.info("App is starting up. Creating background worker...")
    await CollectionsManager.setup()

    # Initialize Neo4j connection (best-effort – graph features degrade gracefully)
    try:
        from langconnect.database.neo4j.connection import get_neo4j_driver

        await get_neo4j_driver()
        logger.info("Neo4j connection established.")
    except Exception:
        logger.warning("Neo4j is not available – graph features will be disabled.")

    yield

    # Shutdown
    try:
        from langconnect.database.neo4j.connection import close_neo4j_driver

        await close_neo4j_driver()
    except Exception:
        pass

    try:
        from langconnect.database.postgres.engine import close_db_engine

        await close_db_engine()
    except Exception:
        pass

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

# Include API routers
APP.include_router(collections_router)
APP.include_router(documents_router)
APP.include_router(graph_router)


@APP.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("langconnect.server:APP", host="0.0.0.0", port=8080)
