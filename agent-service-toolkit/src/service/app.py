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
from core.db.engine import close_db_engine, get_db_engine
from memory import initialize_database, initialize_store
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
        # Initialise the SQLAlchemy async engine (lazy singleton).
        # This is the main database engine for the application's ORM tables
        # (assistant, thread, sync_schedules, datasource_airbyte_mapping, etc.).
        if settings.DATABASE_TYPE.value == "postgres":
            _sa_engine = get_db_engine()
            logger.info("SQLAlchemy async engine ready: %s", _sa_engine.url.database)

        from .store import set_global_store

        # Mark the global store as "ready" (backward compat flag for
        # any code that still checks ``get_store()`` truthiness).
        set_global_store(True)

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

                set_global_checkpointer(saver)
                set_global_langgraph_store(langgraph_store)

                # Start the sync queue worker and Airbyte sync listener
                sync_queue = get_sync_queue()
                sync_queue.start()

                # Table creation is now managed by Alembic — no ensure_table() calls

                sync_listener = get_sync_listener()
                sync_listener.start()

                yield

                # Shutdown listener & queue gracefully
                await sync_listener.stop()
                await sync_queue.stop()

        # Dispose the SQLAlchemy async engine on shutdown
        await close_db_engine()

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
from service.ingest_routes import router as ingest_router  # noqa: E402

app.include_router(datasources_router)
app.include_router(schedule_router)
app.include_router(agent_router)
app.include_router(assistant_router)
app.include_router(assistant_schemas_router)
app.include_router(thread_router)
app.include_router(run_router)
app.include_router(proxy_router)
app.include_router(ingest_router)
