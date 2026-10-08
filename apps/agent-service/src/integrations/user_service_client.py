"""Small client for the user-service operations agent-service depends on."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any
import uuid

from cachetools import TTLCache
from config_manager import env
from error_contract import (
    ApplicationError,
    ConfigurationError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
)
import httpx
from localization import get_locale

from core.http import outbound
from core.http.api_versioning import USER_SERVICE_API_PREFIX
from integrations.user_response import read_user_response

DEFAULT_INTERNAL_SERVICE_TOKEN = ""
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Bounded: an unbounded dict here grew one entry per Keycloak subject ever
# resolved, for the lifetime of the process.
_USER_BY_KEYCLOAK_ID_CACHE: TTLCache[str, dict[str, Any] | None] = TTLCache(maxsize=10_000, ttl=300)
_CURRENT_ACCESS_TOKEN: ContextVar[str | None] = ContextVar(
    "user_service_access_token",
    default=None,
)

DEFAULT_USER_SETTINGS: dict[str, Any] = {
    "theme_preference": None,
    "chat_background": None,
    "default_model": None,
    "default_provider_id": None,
    "auto_scroll": True,
    "shortcut_enabled": True,
    "default_app_mode": "AUTO",
    "memories": [],
    "use_memories": False,
    "enable_memory_tool": False,
    "user_preferences": "",
    "work_role": "",
    "prompt_shortcuts": [],
    "long_term_memory_enabled": False,
    "extract_memory": True,
}


def _user_service_base_url() -> str:
    configured = env.INTERNAL_USER_SERVICE_URL
    if not configured:
        raise ConfigurationError()
    return str(configured).rstrip("/")


def _is_internal_user_service_path(path: str) -> bool:
    return path.startswith(f"{USER_SERVICE_API_PREFIX}/internal/")


def set_current_access_token(access_token: str | None) -> None:
    _CURRENT_ACCESS_TOKEN.set(access_token)


def get_current_access_token() -> str | None:
    return _CURRENT_ACCESS_TOKEN.get()


def _service_headers(
    *,
    method: str,
    access_token: str | None = None,
    include_internal_token: bool = False,
    include_idempotency_key: bool = True,
    forward_user_token: bool = True,
) -> dict[str, str]:
    resolved_access_token = (access_token or get_current_access_token() or "").strip() if forward_user_token else ""
    headers: dict[str, str] = {"Content-Type": "application/json", "X-Language": get_locale()}
    if resolved_access_token:
        headers["Authorization"] = f"Bearer {resolved_access_token}"

    if include_idempotency_key and method.upper() in _MUTATING_METHODS:
        # user-service's idempotency middleware requires this on several
        # internal write routes (REQUIRED_REPLAY policy, enforced by
        # default) and rejects a request missing it with 400 before the
        # route handler ever runs. Generated once per _request() call and
        # reused across the outbound wrapper's retries, so a transient-failure
        # retry replays under the same key instead of risking a second
        # write landing at user-service.
        headers["Idempotency-Key"] = str(uuid.uuid4())

    if not include_internal_token:
        return headers

    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    if token:
        headers["X-Internal-Service-Token"] = token
    return headers


def _looks_like_keycloak_subject(identifier: str) -> bool:
    """Keycloak's built-in user id is a UUID; dev placeholders should not hit user-service."""
    try:
        uuid.UUID(identifier)
    except (TypeError, ValueError):
        return False
    return True


async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    access_token: str | None = None,
    include_internal_token: bool = False,
    timeout: float = 15.0,
    idempotency_key: str | None = None,
    forward_user_token: bool = True,
) -> Any:
    url = f"{_user_service_base_url()}{path}"
    headers = _service_headers(
        method=method,
        access_token=access_token,
        include_internal_token=include_internal_token or _is_internal_user_service_path(path),
        include_idempotency_key=path != f"{USER_SERVICE_API_PREFIX}/internal/users/authorize",
        forward_user_token=forward_user_token,
    )
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    try:
        resp = await outbound.request(
            "user-service",
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=timeout,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise DependencyTimeoutError() from exc
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError(
            code="user_service.request_failed",
            message_key="errors.dependency.unavailable",
        ) from exc

    return read_user_response(resp)


async def get_user_settings(user_id: str, access_token: str | None = None) -> dict[str, Any]:
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/settings",
        access_token=access_token,
    )
    if isinstance(data, dict):
        merged = dict(DEFAULT_USER_SETTINGS)
        merged.update(data)
        return merged
    raise DependencyResponseError()


async def get_current_user(access_token: str) -> dict[str, Any] | None:
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/auth/me",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return None


async def get_users_by_ids(
    user_ids: list[str],
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch matching user snapshots through user-service's internal batch API."""
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/batch",
        json_body={"user_ids": user_ids},
        access_token=access_token,
        include_internal_token=access_token is None,
        idempotency_key=str(uuid.uuid4()),
    )
    if isinstance(data, list):
        return [user for user in data if isinstance(user, dict)]
    return []


async def upsert_user_from_keycloak(
    keycloak_id: str,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Create or update user in user-microservice from Keycloak profile."""
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/upsert-from-keycloak",
        json_body={
            "keycloak_id": keycloak_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
        },
        access_token=access_token,
        include_internal_token=access_token is None,
    )
    if isinstance(data, dict):
        return data
    return {}


# ---------------------------------------------------------------------------
# Permission check — proxied to user-service internal API
# ---------------------------------------------------------------------------


async def get_user_permissions(user_id: str, access_token: str | None = None) -> dict[str, list[str]]:
    """Return the resolved permission list for a user.

    Calls GET /api/v1/internal/users/{user_id}/permissions on user-service.
    Returns ``{"permissions": [...]}``, or ``{"permissions": []}`` on failure.
    """
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/permissions",
        access_token=access_token,
        include_internal_token=True,
    )
    if isinstance(data, dict):
        return data
    return {"permissions": []}


async def create_audit_log(
    action: str,
    resource: str,
    *,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Write one audit event to user-service's audit_logs table.

    user-service owns the audit schema/retention/export; agent-service has
    no audit infra of its own (P3 Task 19). Never call this without
    handling failure at the caller — an audit write must not be allowed to
    break the operation it's recording.
    """
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/audit-logs",
        json_body={
            "action": action,
            "resource": resource,
            "user_id": user_id,
            "details": details or {},
        },
        access_token=access_token,
        include_internal_token=True,
    )
    if isinstance(data, dict):
        return data
    return {}


async def authorize_user_permission(
    user_id: str,
    permission: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Return whether a user has a specific permission."""
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/authorize",
        json_body={"target_id": user_id, "permission": permission},
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {"allowed": False, "permission": permission}


# ---------------------------------------------------------------------------
# User memory operations — proxied to user-service internal API
#
# Recall no longer goes through user-service at all: memory.long_term.
# recall_memories calls rag-service's semantic search directly. Manual
# fact CRUD (create/update/delete/list) is served by user-service's own
# public /users/me/memories API, not proxied through agent-service -- the
# only write path left here is auto-extraction's bulk add.
# ---------------------------------------------------------------------------


async def add_facts_to_user(
    user_id: str,
    contents: list[str],
    source: str = "auto_extracted",
    access_token: str | None = None,
    language: str = "",
) -> list[dict[str, Any]]:
    """Bulk-add auto-extracted facts (deduped server-side).

    `language` is omitted from the body when empty rather than sent as "":
    the column is nullable because "we do not know" is a distinct state from
    any particular language, and an empty string would record a guess.
    """
    body: dict[str, Any] = {"contents": contents, "source": source}
    if language:
        body["language"] = language

    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/bulk",
        json_body=body,
        access_token=access_token,
    )
    if isinstance(data, list):
        return data
    return []


# ---------------------------------------------------------------------------
# Connector configurations — stored per user, encrypted, in user-service
#
# These calls are service-to-service by design: user-service refuses a user
# JWT on these routes, and a sync started by the scheduler has no user at all.
# The forwarded bearer token is therefore left out, so a long-running job never
# depends on a token that expired while it ran.
# ---------------------------------------------------------------------------


def connector_config_owner_id(user_id: str) -> str:
    """The user-service owner key for a principal.

    user-service keys the rows by UUID. A real user id already is one; any other
    principal (the development user, a service caller) owns its configurations
    under a UUID derived from its name, so the same principal always maps to the
    same owner.
    """
    try:
        return str(uuid.UUID(str(user_id)))
    except (TypeError, ValueError):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agenticai:connector-owner:{user_id}"))


def _connector_configs_path(owner_id: str, config_id: str | None = None) -> str:
    base = f"{USER_SERVICE_API_PREFIX}/internal/users/{owner_id}/connector-configs"
    return f"{base}/{config_id}" if config_id else base


async def create_connector_config(
    owner_id: str,
    connector_name: str,
    name: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Store a configuration for ``owner_id``; returns its metadata (``id``, ...)."""
    return await _request(
        "POST",
        _connector_configs_path(owner_id),
        json_body={"connector_name": connector_name, "name": name, "config": config},
        forward_user_token=False,
    )


async def list_connector_configs(owner_id: str) -> list[dict[str, Any]]:
    """Metadata (``id``, ``connector_name``, ``name``, ...) of every stored configuration
    of ``owner_id``. Never the configurations themselves: nothing secret travels."""
    data = await _request("GET", _connector_configs_path(owner_id), forward_user_token=False)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


async def get_connector_config(owner_id: str, config_id: str) -> dict[str, Any] | None:
    """Metadata plus the decrypted ``config``, or ``None`` when it does not exist."""
    try:
        data = await _request(
            "GET",
            _connector_configs_path(owner_id, config_id),
            forward_user_token=False,
        )
    except ApplicationError as exc:
        if exc.status_code == 404:
            return None
        raise
    return data if isinstance(data, dict) else None


async def update_connector_config(
    owner_id: str,
    config_id: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rename and/or replace a stored configuration; returns its metadata."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if config is not None:
        body["config"] = config
    return await _request(
        "PUT",
        _connector_configs_path(owner_id, config_id),
        json_body=body,
        forward_user_token=False,
    )


async def delete_connector_config(owner_id: str, config_id: str) -> None:
    """Delete a stored configuration. A row that is already gone is not an error."""
    try:
        await _request(
            "DELETE",
            _connector_configs_path(owner_id, config_id),
            forward_user_token=False,
        )
    except ApplicationError as exc:
        if exc.status_code != 404:
            raise


async def get_user_by_keycloak_id(
    keycloak_id: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Fetch user from user-service by Keycloak ID (subject)."""
    normalized = str(keycloak_id or "").strip()
    if not normalized or not _looks_like_keycloak_subject(normalized):
        return None
    effective_access_token = (access_token or get_current_access_token() or "").strip()
    use_cache = not effective_access_token
    if use_cache and normalized in _USER_BY_KEYCLOAK_ID_CACHE:
        return _USER_BY_KEYCLOAK_ID_CACHE[normalized]

    try:
        data = await _request(
            "GET",
            f"{USER_SERVICE_API_PREFIX}/internal/users/by-keycloak-id/{normalized}",
            access_token=effective_access_token,
        )
        if isinstance(data, dict):
            if use_cache:
                _USER_BY_KEYCLOAK_ID_CACHE[normalized] = data
            return data
        if use_cache:
            _USER_BY_KEYCLOAK_ID_CACHE[normalized] = None
        return None
    except ApplicationError as exc:
        if exc.status_code == 404:
            if use_cache:
                _USER_BY_KEYCLOAK_ID_CACHE[normalized] = None
            return None
        raise
