"""Small client for user-service settings operations used by agent-service."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import HTTPException, status

from core.env import env

DEFAULT_INTERNAL_SERVICE_TOKEN = "dev-internal-service-token-change-me"
_USER_BY_KEYCLOAK_ID_CACHE: dict[str, dict[str, Any] | None] = {}

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
    "prompt_shortcuts": [],
    "long_term_memory_enabled": False,
    "extract_memory": True,
}


def _user_service_base_url() -> str:
    return str(env.get("USER_SERVICE_URL", "http://localhost:8090")).rstrip("/")


def _internal_headers() -> dict[str, str]:
    token = str(
        env.get("INTERNAL_SERVICE_TOKEN")
        or env.get("USER_SERVICE_INTERNAL_TOKEN")
        or DEFAULT_INTERNAL_SERVICE_TOKEN
    ).strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
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
    timeout: float = 15.0,
) -> Any:
    url = f"{_user_service_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method,
                url,
                headers=_internal_headers(),
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


async def get_user_settings(user_id: str) -> dict[str, Any]:
    data = await _request("GET", f"/api/users/me/settings/internal/users/{user_id}/settings")
    if isinstance(data, dict):
        merged = dict(DEFAULT_USER_SETTINGS)
        merged.update(data)
        return merged
    return dict(DEFAULT_USER_SETTINGS)


async def update_user_settings(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    data = await _request(
        "PATCH",
        f"/api/users/me/settings/internal/users/{user_id}/settings",
        json_body=updates,
    )
    if isinstance(data, dict):
        merged = dict(DEFAULT_USER_SETTINGS)
        merged.update(data)
        return merged
    return dict(DEFAULT_USER_SETTINGS)


async def create_prompt_shortcut(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = await _request(
        "POST",
        f"/api/users/me/settings/internal/users/{user_id}/settings/prompt-shortcuts",
        json_body=payload,
    )
    if isinstance(data, dict):
        return data
    return {}


async def update_prompt_shortcut(
    user_id: str,
    prompt_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    data = await _request(
        "PATCH",
        f"/api/users/me/settings/internal/users/{user_id}/settings/prompt-shortcuts/{prompt_id}",
        json_body=payload,
    )
    if isinstance(data, dict):
        return data
    return {}


async def delete_prompt_shortcut(user_id: str, prompt_id: int) -> dict[str, Any]:
    data = await _request(
        "DELETE",
        f"/api/users/me/settings/internal/users/{user_id}/settings/prompt-shortcuts/{prompt_id}",
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
) -> dict[str, Any]:
    """Create or update user in user-microservice from Keycloak profile."""
    data = await _request(
        "POST",
        "/api/users/internal/upsert-from-keycloak",
        json_body={
            "keycloak_id": keycloak_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
        },
    )
    if isinstance(data, dict):
        return data
    return {}


async def get_user_by_keycloak_id(keycloak_id: str) -> dict[str, Any] | None:
    """Fetch user from user-service by Keycloak ID (subject)."""
    normalized = str(keycloak_id or "").strip()
    if not normalized or not _looks_like_keycloak_subject(normalized):
        return None
    if normalized in _USER_BY_KEYCLOAK_ID_CACHE:
        return _USER_BY_KEYCLOAK_ID_CACHE[normalized]

    try:
        data = await _request(
            "GET",
            f"/api/users/internal/by-keycloak-id/{normalized}",
        )
        if isinstance(data, dict):
            _USER_BY_KEYCLOAK_ID_CACHE[normalized] = data
            return data
        _USER_BY_KEYCLOAK_ID_CACHE[normalized] = None
        return None
    except HTTPException as exc:
        if exc.status_code == 404:
            _USER_BY_KEYCLOAK_ID_CACHE[normalized] = None
            return None
        raise
