import json
from typing import Any

from fastapi import Request
from idempotency import (
    IdempotencyConfig,
    IdempotencyMiddleware,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)
from metrics import install_idempotency_recorder
from starlette.responses import Response

from src.core.api_versioning import API_PREFIX
from src.core.idempotency_principal import extract_principal_from_gateway
from src.core.response_models import ErrorModel, ResponseModel


def build_idempotency_config(settings: Any) -> IdempotencyConfig:
    return IdempotencyConfig(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_db=settings.REDIS_DB,
        redis_password=settings.REDIS_PASSWORD or "",
        idempotency_ttl=settings.IDEMPOTENCY_TTL,
        idempotency_enabled=settings.IDEMPOTENCY_ENABLED,
        lock_ttl=settings.IDEMPOTENCY_LOCK_TTL,
        wait_timeout=settings.IDEMPOTENCY_WAIT_TIMEOUT,
        service_name="user-service",
        decision_recorder=install_idempotency_recorder("user-service"),
        principal_extractor=extract_principal_from_gateway,
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
            # Connector configurations
            "/internal/users/{user_id}/connector-configs",
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
            "/roles/{role_id}/permissions",
            "/roles/{role_id}/role-ids",
            "/coarse-roles/{role_id}/permissions",
            # Resource permissions
            "/permissions/",
            "/permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}",
            # Connector configurations
            "/internal/users/{user_id}/connector-configs/{config_id}",
        ],
        "PATCH": [
            # User profile updates
            "/users/me",
            "/users/{target_id}",
            "/internal/users/{target_id}",
            # Organization updates
            "/organizations/{org_id}",
            # Role updates
            "/coarse-roles/{role_id}",
            "/roles/{role_id}",
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
            "/coarse-roles/{role_id}",
            "/roles/{role_id}",
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
            # Connector configurations
            "/internal/users/{user_id}/connector-configs/{config_id}",
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


class UserResponseIdempotencyMiddleware(IdempotencyMiddleware):
    """Retain idempotency policy and headers with service-local JSON errors."""

    @staticmethod
    def _error_response(status_code: int, code: str, message: str, *, request: Request | None = None) -> Response:
        original = IdempotencyMiddleware._error_response(status_code, code, message, request=request)
        error = json.loads(original.body)["error"]
        model = ResponseModel[None](
            statusCode=status_code,
            message=error["message"],
            error=ErrorModel(code=error["code"], message=error["message"]),
        )
        headers = dict(original.headers)
        headers.pop("content-length", None)
        return Response(
            model.model_dump_json(),
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )
