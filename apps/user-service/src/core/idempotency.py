from typing import Any

from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)

from src.core.api_versioning import API_PREFIX
from src.core.idempotency_principal import extract_principal_from_jwt


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
        principal_extractor=extract_principal_from_jwt,
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
    # High-risk operations: password changes, permission/role mutations,
    # organizational changes, and external sync operations.
    domain_required = {
        "POST": [
            # Password operations
            "/users/invite",
            "/users/me/password",
            "/users/{target_id}/reset-password",
            "/users/{target_id}/password",
            # Permission sync
            "/permissions/sync",
            "/roles/sync-keycloak",
            "/system-settings/keycloak/external-idp/sync",
            "/auth/sync-users",
            # API keys
            "/users/me/api-keys/",
            # Organization and permission side effects
            "/organizations/{org_id}/move",
            "/permissions/resources/{resource_type}/{resource_id}/bulk-grant",
        ],
        "PATCH": [
            # User active state changes
            "/users/{target_id}/active",
            # System settings
            "/system-settings/keycloak",
            "/system-settings/keycloak/realm-session",
        ],
        "DELETE": [
            # Personal API key delete
            "/users/me/api-keys/{key_id}",
        ],
    }
    # Deterministic creates and updates that can be safely replayed.
    required_replay = {
        "POST": [
            # Auth
            "/auth/register",
            # Users
            "/users/",
            "/users/internal/upsert-from-keycloak",
            "/internal/users/batch",
            "/internal/users/upsert-from-keycloak",
            # Roles
            "/roles/",
            "/coarse-roles/",
            # Organizations
            "/organizations",
            "/organizations/{org_id}/users",
            "/organizations/{org_id}/users/bulk",
            "/users/{target_user_id}/organizations/{org_id}/set-primary",
            # Memories
            "/users/me/memories",
            "/users/me/memories/",
            "/internal/users/{target_id}/memories",
            "/internal/users/{target_id}/memories/bulk",
            # Settings
            "/users/me/settings/prompt-shortcuts",
            "/internal/users/{target_id}/settings/prompt-shortcuts",
            # User role assignments
            "/users/{target_id}/role",
            "/users/{target_id}/roles",
            "/users/{target_id}/roles/{role_id}/primary",
            # Resource permissions
            "/organizations/{org_id}/resources",
            "/users/{target_user_id}/resources",
            "/permissions/organizations/{org_id}/resources",
            "/permissions/users/{target_user_id}/resources",
        ],
        "PUT": [
            # Role permission updates
            "/roles/{role_name}/permissions",
            "/roles/{role_name}/role-ids",
            "/roles/{role_name}/inherited-roles",
            "/coarse-roles/{role_name}/permissions",
            # Organization layout
            "/organizations/layout",
            # Resource permissions
            "/permissions/",
            "/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
        ],
        "PATCH": [
            # User profile updates
            "/users/me",
            "/users/{target_id}",
            "/internal/users/{target_id}",
            # Organization updates
            "/organizations/{org_id}",
            # Role updates
            "/coarse-roles/{role_name}",
            "/roles/{role_name}",
            # Settings
            "/users/me/settings/",
            "/users/me/settings/prompt-shortcuts/{shortcut_id}",
            "/settings/",
            "/settings/prompt-shortcuts/{shortcut_id}",
            "/internal/users/{target_id}/settings",
            "/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}",
            # Permission updates
            "/permissions/{permission_id}",
            "/permissions/permissions/{permission_id}",
            # Memories
            "/users/me/memories/{memory_id}",
            "/internal/users/{target_id}/memories/{memory_id}",
            # Organization membership
            "/organizations/{org_id}/users/{target_user_id}",
        ],
        "DELETE": [
            # User deletion
            "/users/{target_id}",
            "/users/{target_id}/roles/{role_id}",
            # Role deletion
            "/coarse-roles/{role_name}",
            "/roles/{role_name}",
            # Organization deletion
            "/organizations/{org_id}",
            # Organization membership
            "/organizations/{org_id}/users/{target_user_id}",
            # Memories
            "/users/me/memories",
            "/users/me/memories/{memory_id}",
            "/users/me/memories/",
            "/internal/users/{target_id}/memories/{memory_id}",
            "/internal/users/{target_id}/memories",
            # Settings
            "/users/me/settings/prompt-shortcuts/{shortcut_id}",
            "/settings/prompt-shortcuts/{shortcut_id}",
            "/internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}",
            # Resource permissions
            "/permissions/{permission_id}",
            "/permissions/permissions/{permission_id}",
        ],
    }
    # Read-like POST endpoints where a missing key is acceptable.
    optional_replay = {
        "POST": [
            # Permission check
            "/permissions/check",
            "/internal/users/authorize",
            # Audit append from another service: the emitter is fire-and-forget
            # and a replayed write is harmless, so a key is accepted but not
            # required.
            "/internal/audit-logs",
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
            # domain_required always enforces a key; other modes fall back to
            # the global enforce_required_keys flag (None).
            enforce_missing_key=(True if mode == IdempotencyMode.DOMAIN_REQUIRED else None),
        )
        for method, paths in routes_by_method.items()
        for path in paths
    ]
