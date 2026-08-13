import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from i18n import I18nMiddleware, init_service_i18n
from idempotency import AsyncRedisPool, IdempotencyConfig, IdempotencyMiddleware

from src.config import get_settings
from src.core.api_versioning import API_PREFIX
from src.core.database.engine import close_db_engine

_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_service_i18n(locales_dir)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.service.system_settings_service import get_system_settings_service

        system_settings = get_system_settings_service()
        await system_settings.load_runtime_settings()
        if system_settings.keycloak.is_enabled():
            try:
                login_client_result = await system_settings.keycloak.ensure_login_client_config()
                logger.info("Keycloak login client bootstrap: %s", login_client_result)
            except Exception:
                logger.exception("Keycloak login client bootstrap failed (non-fatal)")

            if system_settings.keycloak.is_external_keycloak():
                try:
                    result = await system_settings.keycloak.ensure_external_identity_provider()
                    logger.info("External Keycloak identity provider sync result: %s", result)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401, 403):
                        logger.warning(
                            "Skipping external Keycloak identity provider sync: "
                            "admin API access was denied by the configured Keycloak"
                        )
                    else:
                        raise
    except Exception:
        logger.exception("Failed to initialize Keycloak system settings")
    await AsyncRedisPool.connect(_idempotency_config)
    yield
    await AsyncRedisPool.close()
    await close_db_engine()


def _build_idempotency_config() -> IdempotencyConfig:
    s = get_settings()
    return IdempotencyConfig(
        redis_host=s.REDIS_HOST,
        redis_port=s.REDIS_PORT,
        redis_db=s.REDIS_DB,
        redis_password=s.REDIS_PASSWORD,
        idempotency_ttl=s.IDEMPOTENCY_TTL,
        idempotency_enabled=s.IDEMPOTENCY_ENABLED,
        service_name="user-service",
    )


_idempotency_config = _build_idempotency_config()

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="User Service",
        description="User Management Microservice — Auth, Users, Roles, Permissions",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(I18nMiddleware)

    app.add_middleware(
        IdempotencyMiddleware,
        config=_idempotency_config,
        exclude_paths={
            f"{API_PREFIX}/health",
            f"{API_PREFIX}/health/",
            f"{API_PREFIX}/health/ready",
        },
    )


    from src.api.routes import (
        api_keys_router,
        auth_base_router,
        auth_own_router,
        coarse_roles_router,
        internal_settings_router,
        internal_user_memory_router,
        internal_user_router,
        permissions_router,
        roles_router,
        settings_router,
        system_settings_router,
        user_memory_router,
        user_router,
    )
    from src.api.routes.health import router as health_router

    app.include_router(health_router, prefix=f"{API_PREFIX}/health")
    app.include_router(auth_base_router, prefix=API_PREFIX)
    app.include_router(auth_own_router, prefix=API_PREFIX)
    app.include_router(user_router, prefix=API_PREFIX)
    app.include_router(internal_user_router, prefix=API_PREFIX)
    app.include_router(settings_router, prefix=API_PREFIX)
    app.include_router(internal_settings_router, prefix=API_PREFIX)
    app.include_router(user_memory_router, prefix=API_PREFIX)
    app.include_router(internal_user_memory_router, prefix=API_PREFIX)
    app.include_router(api_keys_router, prefix=API_PREFIX)
    app.include_router(coarse_roles_router, prefix=API_PREFIX)
    app.include_router(roles_router, prefix=API_PREFIX)
    app.include_router(permissions_router, prefix=API_PREFIX)
    app.include_router(system_settings_router, prefix=API_PREFIX)

    return app


app = create_app()
