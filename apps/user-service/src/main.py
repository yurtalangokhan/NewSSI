import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from i18n import I18nMiddleware, init_service_i18n
from idempotency import AsyncRedisPool, IdempotencyConfig, IdempotencyMiddleware

from src.config import get_settings
from src.core.api_versioning import API_PREFIX
from src.core.database.engine import close_db_engine
from src.core.database.startup import run_startup_migrations
from src.core.idempotency import build_idempotency_config, build_idempotency_exclude_paths

_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_service_i18n(locales_dir)

logger = logging.getLogger(__name__)


def _admin_email(settings) -> str | None:
    email = settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or settings.KEYCLOAK_ADMIN_EMAIL
    return email.strip().lower() if email and email.strip() else None


def _admin_password(settings) -> str | None:
    password = settings.KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD
    return password.strip() if password and password.strip() else None


def _username_from_email(email: str) -> str:
    return email.split("@", 1)[0] or email


async def _ensure_default_admin(
    *,
    settings,
    keycloak,
    role_repo,
    user_repo,
    settings_repo,
) -> dict[str, Any]:
    if not keycloak.is_enabled():
        return {"status": "skipped", "reason": "Keycloak is disabled"}

    admin_email = _admin_email(settings)
    if not admin_email:
        raise ValueError("KEYCLOAK_ADMIN_EMAIL or KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL must be set")

    admin_role = await role_repo.get_default_admin_role()
    if not admin_role:
        raise ValueError("No default admin role exists in the permission catalog")

    username = _username_from_email(admin_email)
    existing_user = await keycloak.get_user_by_email(admin_email)
    keycloak_id = str((existing_user or {}).get("id") or "")
    action = "exists"

    payload = {
        "email": admin_email,
        "username": username,
        "firstName": "Default",
        "lastName": "Admin",
        "enabled": True,
        "emailVerified": True,
        "requiredActions": [],
    }

    if existing_user:
        await keycloak.update_user(keycloak_id, {**existing_user, **payload})
        action = "updated"
    else:
        password = _admin_password(settings)
        if not password:
            raise ValueError(
                "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD must be set to create the default admin"
            )
        keycloak_id = await keycloak.create_user(
            {
                **payload,
                "credentials": [
                    {
                        "type": "password",
                        "value": password,
                        "temporary": False,
                    }
                ],
            }
        )
        if not keycloak_id:
            raise ValueError("Keycloak default admin user could not be created")
        action = "created"

    password = _admin_password(settings)
    if password and existing_user:
        password_set = await keycloak.set_password(keycloak_id, password, temporary=False)
        if not password_set:
            raise ValueError("Keycloak default admin password could not be set")

    role_name = str(admin_role.name)
    role_set = await keycloak.set_realm_role(keycloak_id, role_name)
    if not role_set:
        raise ValueError("Keycloak default admin role could not be assigned")

    user = await user_repo.upsert_by_keycloak_id(
        keycloak_id,
        email=admin_email,
        username=username,
        first_name="Default",
        last_name="Admin",
        role=role_name,
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )
    await settings_repo.ensure_defaults(user.id)

    return {"status": action, "email": admin_email, "role": role_name}


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_startup_migrations()
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

            try:
                from src.repository import (
                    CompositeRoleRepository,
                    UserRepository,
                    UserSettingsRepository,
                )
                from src.service.role_service import get_composite_role_service

                role_sync_result = await get_composite_role_service().sync_to_keycloak()
                logger.info("Keycloak role catalog sync result: %s", role_sync_result)
                admin_bootstrap_result = await _ensure_default_admin(
                    settings=get_settings(),
                    keycloak=system_settings.keycloak,
                    role_repo=CompositeRoleRepository(),
                    user_repo=UserRepository(),
                    settings_repo=UserSettingsRepository(),
                )
                logger.info("Keycloak default admin bootstrap: %s", admin_bootstrap_result)
            except Exception:
                logger.exception("Keycloak default admin bootstrap failed")
                raise

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
        raise
    await AsyncRedisPool.connect(_idempotency_config)
    yield
    await AsyncRedisPool.close()
    await close_db_engine()


def _build_idempotency_config() -> IdempotencyConfig:
    return build_idempotency_config(get_settings())


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
        exclude_paths=build_idempotency_exclude_paths(API_PREFIX),
    )

    from src.api.routes import (
        api_keys_router,
        auth_base_router,
        auth_own_router,
        coarse_roles_router,
        internal_settings_router,
        internal_user_memory_router,
        internal_user_router,
        organizations_router,
        permissions_router,
        resource_permissions_router,
        roles_router,
        settings_router,
        system_settings_router,
        user_memory_router,
        user_organizations_router,
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
    app.include_router(resource_permissions_router, prefix=API_PREFIX)
    app.include_router(organizations_router, prefix=API_PREFIX)
    app.include_router(user_organizations_router, prefix=API_PREFIX)
    app.include_router(system_settings_router, prefix=API_PREFIX)

    return app


app = create_app()
