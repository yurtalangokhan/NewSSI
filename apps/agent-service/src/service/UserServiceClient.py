"""Small client for user-service settings operations used by agent-service."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

import httpx
from fastapi import HTTPException, status

from core.api_versioning import USER_SERVICE_API_PREFIX
from core.env import env

DEFAULT_INTERNAL_SERVICE_TOKEN = ""
_USER_BY_KEYCLOAK_ID_CACHE: dict[str, dict[str, Any] | None] = {}
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
    return str(env.get("USER_SERVICE_URL", "http://localhost:8090")).rstrip("/")


def _is_internal_user_service_path(path: str) -> bool:
    return path.startswith(f"{USER_SERVICE_API_PREFIX}/internal/")


def set_current_access_token(access_token: str | None) -> None:
    _CURRENT_ACCESS_TOKEN.set(access_token)


def get_current_access_token() -> str | None:
    return _CURRENT_ACCESS_TOKEN.get()


def _service_headers(
    *,
    access_token: str | None = None,
    include_internal_token: bool = False,
) -> dict[str, str]:
    resolved_access_token = (access_token or get_current_access_token() or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if resolved_access_token:
        headers["Authorization"] = f"Bearer {resolved_access_token}"

    if not include_internal_token:
        return headers

    token = str(env.get("INTERNAL_SERVICE_TOKEN") or "").strip()
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
) -> Any:
    url = f"{_user_service_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method,
                url,
                headers=_service_headers(
                    access_token=access_token,
                    include_internal_token=include_internal_token
                    or _is_internal_user_service_path(path),
                ),
                json=json_body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User service request failed: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"User service error: {resp.text}",
        )

    if not resp.content:
        return {}

    try:
        return resp.json()
    except ValueError:
        return {}


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
    return dict(DEFAULT_USER_SETTINGS)


async def get_current_user(access_token: str) -> dict[str, Any] | None:
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/auth/me",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return None


async def update_user_settings(
    user_id: str,
    updates: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "PATCH",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/settings",
        json_body=updates,
        access_token=access_token,
    )
    if isinstance(data, dict):
        merged = dict(DEFAULT_USER_SETTINGS)
        merged.update(data)
        return merged
    return dict(DEFAULT_USER_SETTINGS)


async def update_user_profile(
    user_id: str,
    updates: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "PATCH",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}",
        json_body=updates,
        access_token=access_token,
    )
    _USER_BY_KEYCLOAK_ID_CACHE.pop(str(user_id), None)
    if isinstance(data, dict):
        keycloak_id = data.get("keycloak_id")
        if keycloak_id:
            _USER_BY_KEYCLOAK_ID_CACHE.pop(str(keycloak_id), None)
        return data
    return {}


async def create_prompt_shortcut(
    user_id: str,
    payload: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/settings/prompt-shortcuts",
        json_body=payload,
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {}


async def update_prompt_shortcut(
    user_id: str,
    prompt_id: int,
    payload: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "PATCH",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/settings/prompt-shortcuts/{prompt_id}",
        json_body=payload,
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {}


async def delete_prompt_shortcut(
    user_id: str,
    prompt_id: int,
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "DELETE",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/settings/prompt-shortcuts/{prompt_id}",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {"success": True}


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


async def get_user_permissions(
    user_id: str, access_token: str | None = None
) -> dict[str, list[str]]:
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
# ---------------------------------------------------------------------------


async def get_user_memories_for_recall(user_id: str, access_token: str | None = None) -> list[str]:
    """Return memory content strings for prompt injection."""
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/recall",
        access_token=access_token,
    )
    if isinstance(data, list):
        return data
    return []


async def get_user_memories(
    user_id: str,
    page: int = 1,
    page_size: int = 50,
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories?page={page}&page_size={page_size}",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {"items": [], "total": 0}


async def get_user_memory(
    memory_id: str,
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    data = await _request(
        "GET",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/{memory_id}",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return None


async def create_user_memory(
    user_id: str,
    content: str,
    access_token: str | None = None,
) -> dict[str, Any]:
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories",
        json_body={"content": content},
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return {}


async def add_facts_to_user(
    user_id: str,
    contents: list[str],
    source: str = "auto_extracted",
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    """Bulk-add auto-extracted facts (deduped server-side)."""
    data = await _request(
        "POST",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/bulk",
        json_body={"contents": contents, "source": source},
        access_token=access_token,
    )
    if isinstance(data, list):
        return data
    return []


async def update_user_memory(
    memory_id: str,
    user_id: str,
    content: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    data = await _request(
        "PATCH",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/{memory_id}",
        json_body={"content": content},
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data
    return None


async def delete_user_memory(
    memory_id: str,
    user_id: str,
    access_token: str | None = None,
) -> bool:
    await _request(
        "DELETE",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories/{memory_id}",
        access_token=access_token,
    )
    # 204 → _request returns {}; non-2xx → _request raises
    return True


async def delete_all_user_memories(
    user_id: str,
    access_token: str | None = None,
) -> int:
    data = await _request(
        "DELETE",
        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/memories",
        access_token=access_token,
    )
    if isinstance(data, dict):
        return data.get("deleted", 0)
    return 0


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
    except HTTPException as exc:
        if exc.status_code == 404:
            if use_cache:
                _USER_BY_KEYCLOAK_ID_CACHE[normalized] = None
            return None
        raise
