from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config_manager import env
from error_contract import ERROR_RESPONSES, apply_idempotency_openapi, register_error_handlers
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from idempotency import AsyncRedisPool, IdempotencyConfig
from localization import LocalizationMiddleware, init_localization
from metrics import MetricsMiddleware, metrics_endpoint
from observability import CorrelationMiddleware
from security import close_all as security_close_all, reveal_secret

from src.core.api_versioning import API_PREFIX
from src.core.background_tasks import cancel_all_background_tasks
from src.core.database.engine import close_db_engine
from src.core.database.middleware import RequestScopedSessionMiddleware
from src.core.database.startup import run_startup_migrations
from src.core.idempotency import build_idempotency_config, build_idempotency_exclude_paths
from src.core.observability import (
    DependencyPolicy,
    configure_logging,
    configure_telemetry,
    dependency_error_fields,
    dependency_registry,
    get_logger,
    retry_async,
)

_here = Path(__file__).resolve().parent
locales_dir = _here.parent / "locales"
if not locales_dir.exists():
    locales_dir = _here / "locales"
init_localization(locales_dir)

logger = get_logger(__name__)


def _admin_email(settings) -> str | None:
    email = settings.KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL or settings.KEYCLOAK_ADMIN_EMAIL
    return email.strip().lower() if email and email.strip() else None


def _admin_password(settings) -> str | None:
    return reveal_secret(settings.KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD)


def _username_from_email(email: str) -> str:
    return email.split("@", 1)[0] or email


@dataclass(frozen=True)
class _DegradedDependencyOutcome:
    """Which dependency a bootstrap failure is attributed to, and how it reads in the log."""

    dependency: str
    message: str


def _admin_bootstrap_degraded_dependency(exc: BaseException) -> _DegradedDependencyOutcome:
    """Classify a `_ensure_default_admin` failure honestly, instead of blaming Keycloak by default.

    Its body mixes real Keycloak Admin API calls with local repository calls
    (`role_repo`, `user_repo`, `settings_repo`) that do their own Postgres
    I/O. A blanket "keycloak is unavailable" on any exception at all
    mislabels every one of those local failures as a Keycloak outage -- a
    real `user_settings` foreign-key violation was diagnosed this way,
    sending the investigation toward Keycloak connectivity when Keycloak was
    never involved.

    Only an actual Keycloak HTTP failure (`httpx.HTTPError` and its
    subclasses -- `HTTPStatusError`, `ConnectError`, `TimeoutException`, ...)
    keeps that framing, because it is the one class of failure this call can
    raise that Keycloak reachability actually explains.
    """
    if isinstance(exc, httpx.HTTPError):
        return _DegradedDependencyOutcome(
            dependency="keycloak",
            message=("keycloak is unavailable during default admin bootstrap; continuing without admin user sync."),
        )
    return _DegradedDependencyOutcome(
        dependency="default_admin_bootstrap",
        message=(f"Default admin bootstrap failed ({type(exc).__name__}: {exc}); continuing without admin user sync."),
    )


async def _ensure_default_admin(
    *,
    settings,
    keycloak,
    role_repo,
    user_repo,
    settings_repo,
) -> dict[str, Any]:
    admin_email = _admin_email(settings)
    if not admin_email:
        raise ValueError("KEYCLOAK_ADMIN_EMAIL or KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL must be set")

    admin_role = await role_repo.get_default_admin_role()
    if not admin_role:
        raise ValueError("No default admin role exists in the permission catalog")

    username = _username_from_email(admin_email)
    existing_user = await keycloak.get_user_by_email(admin_email)
    if not existing_user:
        # Keycloak enforces username uniqueness realm-wide regardless of
        # whether email is set -- an account this lookup would otherwise miss
        # (e.g. one the identity cutover import reused rather than overwrote,
        # leaving it without an email) still collides with `create_user`.
        existing_user = await keycloak.get_user_by_username(username)
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

    if not existing_user:
        password = _admin_password(settings)
        if not password:
            raise ValueError("KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD must be set to create the default admin")
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

    role_name = str(admin_role.name)
    if not existing_user:
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
async def lifespan(_app: FastAPI):
    run_startup_migrations()
    dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    try:
        from src.service.system_settings_service import get_system_settings_service

        system_settings = get_system_settings_service()
        await system_settings.load_runtime_settings()
        try:
            login_client_result = await system_settings.keycloak.ensure_login_client_config()
            logger.info("Keycloak login client bootstrap: %s", login_client_result)
        except Exception as exc:
            dependency_registry.record_degraded(
                "keycloak_login_client",
                hint="Login client bootstrap failed; login flow may be degraded.",
            )
            logger.warning(
                "keycloak is unavailable; continuing without login client bootstrap.",
                extra={
                    **dependency_error_fields(exc, dependency="keycloak"),
                    "event": "startup.dependency.degraded",
                    "dependency": "keycloak",
                    "operation": "ensure_login_client_config",
                    "status": "degraded",
                },
            )

        try:
            from src.repository import (
                CompositeRoleRepository,
                UserRepository,
                UserSettingsRepository,
            )
            from src.repository.keycloak_role_client import ensure_identity_user_profile

            await ensure_identity_user_profile()
            admin_bootstrap_result = await _ensure_default_admin(
                settings=env,
                keycloak=system_settings.keycloak,
                role_repo=CompositeRoleRepository(),
                user_repo=UserRepository(),
                settings_repo=UserSettingsRepository(),
            )
            logger.info("Keycloak default admin bootstrap: %s", admin_bootstrap_result)
            dependency_registry.record_ok("keycloak", policy=DependencyPolicy.REQUIRED)
        except Exception as exc:
            outcome = _admin_bootstrap_degraded_dependency(exc)
            dependency_registry.record_degraded(
                outcome.dependency,
                hint="Default admin bootstrap failed; admin user may be missing.",
            )
            logger.warning(
                outcome.message,
                extra={
                    **dependency_error_fields(exc, dependency=outcome.dependency),
                    "event": "startup.dependency.degraded",
                    "dependency": outcome.dependency,
                    "operation": "ensure_default_admin",
                    "status": "degraded",
                },
            )

        if system_settings.keycloak.is_external_keycloak():
            try:
                result = await system_settings.keycloak.ensure_external_identity_provider()
                logger.info("External Keycloak identity provider sync result: %s", result)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    dependency_registry.record_degraded(
                        "keycloak_idp",
                        hint="External IdP sync skipped; admin API access denied.",
                    )
                    logger.warning(
                        "Skipping external Keycloak identity provider sync: "
                        "admin API access was denied by the configured Keycloak"
                    )
                else:
                    raise
            except Exception as exc:
                dependency_registry.record_degraded(
                    "keycloak_idp",
                    hint="External IdP sync skipped; Keycloak unreachable.",
                )
                logger.warning(
                    "Skipping external Keycloak identity provider sync: Keycloak is unreachable.",
                    extra={
                        **dependency_error_fields(exc, dependency="keycloak"),
                        "event": "startup.dependency.degraded",
                        "dependency": "keycloak",
                        "operation": "ensure_external_identity_provider",
                        "status": "degraded",
                    },
                )
    except Exception as exc:
        dependency_registry.record_degraded(
            "keycloak",
            hint="Keycloak system settings could not be initialized; service is running without Keycloak integration.",
        )
        logger.warning(
            "keycloak system settings could not be initialized; continuing without Keycloak integration.",
            extra={
                **dependency_error_fields(exc, dependency="keycloak"),
                "event": "startup.dependency.degraded",
                "dependency": "keycloak",
                "operation": "load_runtime_settings",
                "status": "degraded",
            },
        )
    await reconcile_resource_authorization_startup()
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
    yield
    await AsyncRedisPool.close()
    await close_db_engine()
    await security_close_all()
    await cancel_all_background_tasks()


async def reconcile_resource_authorization_startup(projection=None) -> None:
    """Fail startup when existing instance grants cannot be projected safely."""
    if projection is None:
        from src.repository.keycloak_resource_authorization import (
            ResourceAuthorizationProjectionRepository,
        )

        projection = ResourceAuthorizationProjectionRepository()
    await projection.reconcile_startup()


def _build_idempotency_config() -> IdempotencyConfig:
    return build_idempotency_config(env)


_idempotency_config = _build_idempotency_config()


def _docs_enabled() -> bool:
    """Whether to publish the interactive API docs."""
    return bool(env.ENABLE_API_DOCS)


def create_app() -> FastAPI:
    settings = env
    configure_logging(service_name="user-service", log_level=settings.LOG_LEVEL)
    configure_telemetry()

    app = FastAPI(
        title="User Service",
        description="User Management Microservice — Auth, Users, Roles, Permissions",
        version="1.0.0",
        responses=ERROR_RESPONSES,
        # The interactive docs enumerate every route and schema, including the
        # internal ones. Useful in development, an unnecessary map of the
        # service anywhere else.
        docs_url="/docs" if _docs_enabled() else None,
        redoc_url="/redoc" if _docs_enabled() else None,
        lifespan=lifespan,
    )

    register_error_handlers(app, service_name="user-service")
    from src.core.response_errors import register_response_errors

    # Idempotency declarations first: the response-error registration then
    # rewrites every 4xx/5xx body to this service's own error schema, so the
    # middleware's statuses are documented with the envelope actually sent.
    apply_idempotency_openapi(app)
    register_response_errors(app)

    # Innermost user middleware (added first): scoped as tightly as possible
    # around actual route handling, not wrapping CORS/metrics/idempotency.
    app.add_middleware(RequestScopedSessionMiddleware)

    app.add_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(LocalizationMiddleware)

    from src.core.idempotency import UserResponseIdempotencyMiddleware

    app.add_middleware(
        UserResponseIdempotencyMiddleware,
        config=_idempotency_config,
        exclude_paths=build_idempotency_exclude_paths(API_PREFIX),
    )

    app.add_middleware(CorrelationMiddleware)

    # Registered last, so it is outermost: the counters must observe the
    # responses the idempotency middleware short-circuits, such as a 503 from
    # an unavailable store. Metrics writes no log records, so it needs no
    # correlation id itself.
    app.add_middleware(MetricsMiddleware, service_name="user-service")

    from src.api.routes import (
        api_keys_router,
        auth_base_router,
        auth_own_router,
        coarse_roles_router,
        internal_audit_router,
        internal_connector_configs_router,
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
    app.include_router(internal_connector_configs_router, prefix=API_PREFIX)
    app.include_router(api_keys_router, prefix=API_PREFIX)
    app.include_router(coarse_roles_router, prefix=API_PREFIX)
    app.include_router(roles_router, prefix=API_PREFIX)
    app.include_router(permissions_router, prefix=API_PREFIX)
    app.include_router(resource_permissions_router, prefix=API_PREFIX)
    app.include_router(organizations_router, prefix=API_PREFIX)
    app.include_router(user_organizations_router, prefix=API_PREFIX)
    app.include_router(system_settings_router, prefix=API_PREFIX)
    app.include_router(internal_audit_router, prefix=API_PREFIX)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=env.SERVICE_HOST, port=env.USER_SERVICE_PORT, reload=True)
