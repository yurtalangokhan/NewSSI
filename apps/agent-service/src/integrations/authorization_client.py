"""Authorization checks backed by user-service effective permission assignments."""

from __future__ import annotations

import time

from cachetools import LRUCache
from config_manager import env

from core.exceptions import ApplicationError


class AuthorizationClient:
    def __init__(self) -> None:
        # Bounded: an unbounded dict here grew one entry per (user, permission)
        # pair ever checked, for the lifetime of the process.
        self._permission_cache: LRUCache[tuple[str, str], tuple[bool, float]] = LRUCache(maxsize=10_000)

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
        from integrations.user_service_client import (
            authorize_user_permission,
            get_user_permissions,
        )

        try:
            decision = await authorize_user_permission(user_id, permission, access_token)
            return bool(decision.get("allowed"))
        except ApplicationError:
            try:
                permissions_data = await get_user_permissions(user_id, access_token)
            except ApplicationError:
                # Both lookups failed. Letting the second one's status code
                # (e.g. a raw 401) propagate past this point would surface
                # an internal plumbing failure as if the caller's own
                # session were invalid -- authenticatedFetch treats any 401
                # as an expired session and logs the user out. A permission
                # check that cannot be answered must deny the one action
                # being checked (a normal, expected 403), not end the
                # session over an unrelated dependency hiccup.
                return False
            permissions = permissions_data.get("permissions", [])
            return permissions == ["*"] or permission in permissions

    def _cache_ttl_seconds(self) -> float:
        value = env.USER_PERMISSION_CACHE_TTL_SECONDS or "30"
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
