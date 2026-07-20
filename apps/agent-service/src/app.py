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
from core import settings as core_settings
from core.db import close_db_engine, get_db_engine
from core.db.schema_bootstrap import ensure_schema
from core.logger import configure_logging
from memory import initialize_database, initialize_store
from service.AirbyteSyncListenerService import get_sync_listener
from service.CheckpointerService import set_global_checkpointer
from service.LangGraphStoreService import set_global_langgraph_store
from service.MCPProviderService import MCPProviderService
from service.SyncQueueService import get_sync_queue

warnings.filterwarnings("ignore", category=LangChainBetaWarning)
configure_logging()
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
        if settings.DATABASE_TYPE.value == "postgres":
            _sa_engine = get_db_engine()
            logger.info("SQLAlchemy async engine ready: %s", _sa_engine.url.database)
            await ensure_schema()

        from service.StoreService import set_global_store

        set_global_store(True)

        async with initialize_database() as saver:
            async with initialize_store() as langgraph_store:
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
                mcp_url = str(core_settings.TOOLS_SERVICE_URL)
                await mcp_service.initialize_builtin(mcp_url)
                logger.info(f"MCP Provider initialized: {mcp_url}")

                sync_queue = get_sync_queue()
                sync_queue.start()

                sync_listener = get_sync_listener()
                sync_listener.start()

                yield

                await sync_listener.stop()
                await sync_queue.stop()

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


@app.get("/api/health")
async def api_health_check():
    """API health check endpoint."""
    health_status = {"status": "UP"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status


# =============================================================================
# Include routers (new modular routes)
# =============================================================================

from api.routes import (  # noqa: E402,I001
    agent_definitions_router,
    agent_groups_router,
    agent_tools_router,
    agents_router,
    assistant_schemas_router,
    assistants_router,
    auth_router,
    chat_router,
    datasources_router,
    file_router,
    ingest_router,
    mcp_providers_router,
    mcp_tools_router,
    persona_router,
    provider_router,
    proxy_router,
    run_router,
    schedule_router,
    threads_router,
    user_router,
    web_search_router,
)

app.include_router(agents_router)
app.include_router(agent_definitions_router)
app.include_router(agent_groups_router)
app.include_router(assistants_router)
app.include_router(threads_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(persona_router)
app.include_router(user_router)
app.include_router(schedule_router)
app.include_router(ingest_router)
app.include_router(proxy_router)
app.include_router(run_router)
app.include_router(datasources_router)
app.include_router(assistant_schemas_router)
app.include_router(file_router)
app.include_router(web_search_router)
app.include_router(provider_router)
app.include_router(mcp_providers_router)
app.include_router(mcp_tools_router)
app.include_router(agent_tools_router)
