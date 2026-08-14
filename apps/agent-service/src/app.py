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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from i18n import I18nMiddleware, init_service_i18n
from idempotency import AsyncRedisPool, IdempotencyConfig, IdempotencyMiddleware
from langchain_core._api import LangChainBetaWarning
from langfuse import Langfuse  # type: ignore[import-untyped]

from agents import get_agent, get_all_agent_info, load_agent
from core import settings
from core import settings as core_settings
from core.api_versioning import API_PREFIX
from core.db import close_db_engine, get_db_engine
from core.db.startup import run_startup_migrations
from core.logger import configure_logging
from memory import initialize_database, initialize_store
from service.AirbyteSyncListenerService import get_sync_listener
from service.CheckpointerService import set_global_checkpointer
from service.LangGraphStoreService import set_global_langgraph_store
from service.MCPProviderService import MCPProviderService
from service.SyncQueueService import get_sync_queue

_idempotency_config = IdempotencyConfig(
    redis_host=settings.REDIS_HOST,
    redis_port=settings.REDIS_PORT,
    redis_db=settings.REDIS_DB,
    redis_password=settings.REDIS_PASSWORD,
    idempotency_ttl=settings.IDEMPOTENCY_TTL,
    idempotency_enabled=settings.IDEMPOTENCY_ENABLED,
    service_name="agent-service",
)

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
            run_startup_migrations()
            _sa_engine = get_db_engine()
            logger.info("SQLAlchemy async engine ready: %s", _sa_engine.url.database)

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

                await AsyncRedisPool.connect(_idempotency_config)

                yield

                await AsyncRedisPool.close()
                await sync_listener.stop()
                await sync_queue.stop()

        await close_db_engine()

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
init_service_i18n(locales_dir)

app = FastAPI(lifespan=lifespan, generate_unique_id_function=custom_generate_unique_id)

app.add_middleware(I18nMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Location"],
)


app.add_middleware(
    IdempotencyMiddleware,
    config=_idempotency_config,
    exclude_paths={f"{API_PREFIX}/health"},
)


# =============================================================================
# Health check (on app, not router — no auth required)
# =============================================================================


async def _health_status():
    """Build the agent-service health response."""
    health_status = {"status": "ok"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status


@app.get(f"{API_PREFIX}/health")
async def api_health_check():
    """Versioned health check endpoint."""
    return await _health_status()


def _api_versioned_path(path: str, resource_prefix: str = "") -> str:
    if path.startswith("/api/"):
        return f"{API_PREFIX}{path[4:]}"
    if resource_prefix:
        return f"{API_PREFIX}{resource_prefix}{path}"
    return f"{API_PREFIX}{path}"


def _include_router_with_versioned_routes(router, *, resource_prefix: str = ""):
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        versioned_path = _api_versioned_path(route.path, resource_prefix)
        app.add_api_route(
            versioned_path,
            route.endpoint,
            response_model=route.response_model,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            methods=route.methods,
            operation_id=route.operation_id,
            response_class=route.response_class,
            name=route.name,
            openapi_extra=route.openapi_extra,
        )


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
    mail_configs_router,
    mcp_providers_router,
    mcp_tools_router,
    ollama_router,
    persona_router,
    provider_router,
    proxy_router,
    run_router,
    schedule_router,
    threads_router,
    user_router,
    web_search_router,
)

_include_router_with_versioned_routes(agents_router)
_include_router_with_versioned_routes(agent_definitions_router)
_include_router_with_versioned_routes(agent_groups_router)
_include_router_with_versioned_routes(assistants_router)
_include_router_with_versioned_routes(threads_router)
_include_router_with_versioned_routes(auth_router, resource_prefix="/auth")
_include_router_with_versioned_routes(chat_router)
_include_router_with_versioned_routes(persona_router)
_include_router_with_versioned_routes(user_router)
_include_router_with_versioned_routes(schedule_router)
_include_router_with_versioned_routes(ingest_router, resource_prefix="/ingest")
_include_router_with_versioned_routes(proxy_router)
_include_router_with_versioned_routes(run_router)
_include_router_with_versioned_routes(datasources_router)
_include_router_with_versioned_routes(assistant_schemas_router)
_include_router_with_versioned_routes(file_router)
_include_router_with_versioned_routes(web_search_router)
_include_router_with_versioned_routes(provider_router)
_include_router_with_versioned_routes(ollama_router)
_include_router_with_versioned_routes(mail_configs_router)
_include_router_with_versioned_routes(mcp_providers_router)
_include_router_with_versioned_routes(mcp_tools_router)
_include_router_with_versioned_routes(agent_tools_router)
