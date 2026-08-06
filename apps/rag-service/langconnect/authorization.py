"""Authorization checks backed by user-service effective permission assignments."""

from __future__ import annotations

import time

import httpx

from langconnect import config
from langconnect.api_versioning import USER_SERVICE_API_PREFIX

HTTP_OK = 200


class AuthorizationClient:
    """User-service authorization client with a process-local decision cache."""

    def __init__(self) -> None:
        """Initialize the process-local permission decision cache."""
        self._permission_cache: dict[tuple[str, str], tuple[bool, float]] = {}

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        access_token: str | None = None,
    ) -> bool:
        """Return whether a user has the requested permission."""
        cache_key = (user_id, permission)
        now = time.monotonic()
        cached = self._permission_cache.get(cache_key)
        if cached and now < cached[1]:
            return cached[0]

        allowed = await self._fetch_permission_decision(
            user_id=user_id,
            permission=permission,
            access_token=access_token,
        )
        self._permission_cache[cache_key] = (
            allowed,
            now + config.USER_PERMISSION_CACHE_TTL_SECONDS,
        )
        return allowed

    async def _fetch_permission_decision(
        self,
        *,
        user_id: str,
        permission: str,
        access_token: str | None,
    ) -> bool:
        headers = self._user_service_headers(access_token)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    (
                        f"{config.USER_SERVICE_URL.rstrip('/')}"
                        f"{USER_SERVICE_API_PREFIX}/internal/users/authorize"
                    ),
                    headers=headers,
                    json={"target_id": user_id, "permission": permission},
                )
            if response.status_code == HTTP_OK:
                data = response.json()
                return bool(data.get("allowed")) if isinstance(data, dict) else False
        except (httpx.HTTPError, ValueError):
            pass

        return await self._fallback_to_effective_permissions(
            user_id=user_id,
            permission=permission,
            headers=headers,
        )

    @staticmethod
    def _user_service_headers(access_token: str | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        internal_token = config.INTERNAL_SERVICE_TOKEN.strip()
        if internal_token:
            headers["X-Internal-Service-Token"] = internal_token
        return headers

    async def _fallback_to_effective_permissions(
        self,
        *,
        user_id: str,
        permission: str,
        headers: dict[str, str],
    ) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    (
                        f"{config.USER_SERVICE_URL.rstrip('/')}"
                        f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/permissions"
                    ),
                    headers=headers,
                )
            if response.status_code != HTTP_OK:
                return False
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return False

        raw_permissions = data.get("permissions", []) if isinstance(data, dict) else []
        permissions = [str(item) for item in raw_permissions if item is not None]
        return permissions == ["*"] or permission in permissions


_authorization_client_instance: AuthorizationClient | None = None


def get_authorization_client() -> AuthorizationClient:
    """Return the process-wide authorization client."""
    global _authorization_client_instance
    if _authorization_client_instance is None:
        _authorization_client_instance = AuthorizationClient()
    return _authorization_client_instance
