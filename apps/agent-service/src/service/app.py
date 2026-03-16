"""
FastAPI application factory.

Creates the ``app`` instance, registers lifespan, CORS middleware,
the health-check endpoint, and includes every sub-router.

This is the *only* module that needs to know about all route modules.
"""

import logging
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from langchain_core._api import LangChainBetaWarning
from langfuse import Langfuse  # type: ignore[import-untyped]

from agents import get_agent, get_all_agent_info, load_agent
from core import settings
from memory import initialize_database, initialize_store
from memory.postgres import get_postgres_connection_string
from service.checkpointer import set_global_checkpointer
from service.langgraph_store import set_global_langgraph_store
from service.sync_queue import get_sync_queue
from service.airbyte_sync_listener import get_sync_listener

warnings.filterwarnings("ignore", category=LangChainBetaWarning)
logger = logging.getLogger(__name__)


# =============================================================================
# Helpers
# =============================================================================


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate idiomatic operation IDs for OpenAPI client generation."""
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
    try:
        from .store import PostgresStore, set_global_store

        conn_str = get_postgres_connection_string()
        store = PostgresStore(
            conn_str,
            min_size=settings.POSTGRES_MIN_CONNECTIONS_PER_POOL,
            max_size=settings.POSTGRES_MAX_CONNECTIONS_PER_POOL,
        )
        await store.setup()

        async with initialize_database() as saver:
            if hasattr(saver, "setup"):
                await saver.setup()

            # Initialize the LangGraph store for cross-thread long-term memory
            async with initialize_store() as langgraph_store:
                if hasattr(langgraph_store, "setup"):
                    await langgraph_store.setup()
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
                    # Set the LangGraph store (BaseStore) for long-term memory
                    agent.store = langgraph_store

                set_global_store(store)
                set_global_checkpointer(saver)
                set_global_langgraph_store(langgraph_store)

                # Start the sync queue worker and Airbyte sync listener
                sync_queue = get_sync_queue()
                sync_queue.start()

                # Ensure the mapping table exists
                from service.airbyte_mapping_db import AirbyteMappingDB

                await AirbyteMappingDB.ensure_table()

                sync_listener = get_sync_listener()
                sync_listener.start()

                yield

                # Shutdown listener & queue gracefully
                await sync_listener.stop()
                await sync_queue.stop()

            await store.close()

    except Exception as e:
        logger.error(f"Error during database/store/agents initialization: {e}")
        raise


# =============================================================================
# App instance
# =============================================================================

app = FastAPI(lifespan=lifespan, generate_unique_id_function=custom_generate_unique_id)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Location"],
)


# =============================================================================
# Health check (on app, not router — no auth required)
# =============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = {"status": "ok"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status


# =============================================================================
# Include routers
# =============================================================================

from service.datasources import router as datasources_router  # noqa: E402
from service.schedule_routes import router as schedule_router  # noqa: E402
from service.agent_routes import router as agent_router  # noqa: E402
from service.assistant_routes import router as assistant_router  # noqa: E402
from service.assistant_schemas import router as assistant_schemas_router  # noqa: E402
from service.thread_routes import router as thread_router  # noqa: E402
from service.run_routes import router as run_router  # noqa: E402
from service.proxy_routes import router as proxy_router  # noqa: E402
from service.auth_routes import router as auth_router  # noqa: E402

app.include_router(datasources_router)
app.include_router(schedule_router)
app.include_router(agent_router)
app.include_router(assistant_router)
app.include_router(assistant_schemas_router)
app.include_router(thread_router)
app.include_router(run_router)
app.include_router(proxy_router)
app.include_router(auth_router)
