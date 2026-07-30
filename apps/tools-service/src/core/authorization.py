"""Authorization data fetched from user-service for MCP token scopes."""

from __future__ import annotations

import time

import httpx

from .api_versioning import USER_SERVICE_API_PREFIX
from .settings import get_settings

_PERMISSION_CACHE: dict[str, tuple[float, list[str]]] = {}


def _user_service_base_url() -> str:
    return get_settings().user_service_url


def _permission_cache_ttl() -> float:
    return get_settings().user_permission_cache_ttl_seconds


async def get_user_service_permissions(token: str, subject: str) -> list[str]:
    """Return effective permissions from user-service, cached per subject."""
    now = time.monotonic()
    cached = _PERMISSION_CACHE.get(subject)
    if cached and cached[0] > now:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                (
                    f"{_user_service_base_url().rstrip('/')}"
                    f"{USER_SERVICE_API_PREFIX}/internal/users/{subject}/permissions"
                ),
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    raw_permissions = data.get("permissions", []) if isinstance(data, dict) else []
    permissions = sorted(
        str(permission) for permission in raw_permissions if permission is not None
    )
    _PERMISSION_CACHE[subject] = (now + _permission_cache_ttl(), permissions)
    return permissions
