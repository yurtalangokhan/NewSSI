"""Authorization checks backed by user-service effective permission assignments."""

from __future__ import annotations

import time

from core.env import env
from core.exceptions import ApplicationError


class AuthorizationClient:
    def __init__(self) -> None:
        self._permission_cache: dict[tuple[str, str], tuple[bool, float]] = {}

    async def has_permission(
        self,
        user_id: str,
        permission: str,
        access_token: str | None = None,
    ) -> bool:
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
        self._permission_cache[cache_key] = (allowed, now + self._cache_ttl_seconds())
        return allowed

    async def _fetch_permission_decision(
        self,
        *,
        user_id: str,
        permission: str,
        access_token: str | None,
    ) -> bool:
        from service.UserServiceClient import (
            authorize_user_permission,
            get_user_permissions,
        )

        try:
            decision = await authorize_user_permission(user_id, permission, access_token)
            return bool(decision.get("allowed"))
        except ApplicationError:
            permissions_data = await get_user_permissions(user_id, access_token)
            permissions = permissions_data.get("permissions", [])
            return permissions == ["*"] or permission in permissions

    def _cache_ttl_seconds(self) -> float:
        value = env.get("USER_PERMISSION_CACHE_TTL_SECONDS", "30")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 30.0


_authorization_client_instance: AuthorizationClient | None = None


def get_authorization_client() -> AuthorizationClient:
    global _authorization_client_instance
    if _authorization_client_instance is None:
        _authorization_client_instance = AuthorizationClient()
    return _authorization_client_instance
