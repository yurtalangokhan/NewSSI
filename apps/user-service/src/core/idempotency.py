from typing import Any

from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)

from src.core.api_versioning import API_PREFIX


def build_idempotency_config(settings: Any) -> IdempotencyConfig:
    return IdempotencyConfig(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_db=settings.REDIS_DB,
        redis_password=settings.REDIS_PASSWORD,
        idempotency_ttl=settings.IDEMPOTENCY_TTL,
        idempotency_enabled=settings.IDEMPOTENCY_ENABLED,
        service_name="user-service",
        enforce_required_keys=getattr(settings, "IDEMPOTENCY_ENFORCE_REQUIRED_KEYS", False),
        lock_ttl=getattr(settings, "IDEMPOTENCY_LOCK_TTL", 10),
        wait_timeout=getattr(settings, "IDEMPOTENCY_WAIT_TIMEOUT", 10.0),
        policy=build_idempotency_policy(),
    )


def build_idempotency_exclude_paths(api_prefix: str = API_PREFIX) -> set[str]:
    return {
        f"{api_prefix}/health",
        f"{api_prefix}/health/",
        f"{api_prefix}/health/ready",
    }


def build_idempotency_policy(api_prefix: str = API_PREFIX) -> IdempotencyPolicyConfig:
    excluded = {
        "POST": [
            "/auth/login",
            "/auth/external/login",
            "/auth/logout",
            "/auth/refresh",
        ],
    }
    domain_required = {
        "POST": [
            "/users/invite",
            "/users/{target_id}/reset-password",
            "/users/{target_id}/password",
            "/permissions/sync",
            "/roles/sync-keycloak",
            "/system-settings/keycloak/external-idp/sync",
            "/auth/sync-users",
            "/users/me/api-keys/",
        ],
    }
    required_replay = {
        "POST": [
            "/auth/register",
            "/users/",
            "/roles/",
            "/coarse-roles/",
            "/users/me/memories/",
            "/users/me/settings/prompt-shortcuts",
        ],
    }
    optional_replay = {
        "PATCH": [
            "/users/me/settings/",
        ],
    }

    return IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            *build_route_policies(api_prefix, excluded, IdempotencyMode.EXCLUDED),
            *build_route_policies(api_prefix, domain_required, IdempotencyMode.DOMAIN_REQUIRED),
            *build_route_policies(api_prefix, required_replay, IdempotencyMode.REQUIRED_REPLAY),
            *build_route_policies(api_prefix, optional_replay, IdempotencyMode.OPTIONAL_REPLAY),
        ],
    )


def build_route_policies(
    api_prefix: str,
    routes_by_method: dict[str, list[str]],
    mode: IdempotencyMode,
) -> list[IdempotencyPolicy]:
    return [
        IdempotencyPolicy(
            method=method,
            path=f"{api_prefix}{path}",
            mode=mode,
            enforce_missing_key=mode == IdempotencyMode.DOMAIN_REQUIRED,
        )
        for method, paths in routes_by_method.items()
        for path in paths
    ]
