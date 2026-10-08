"""Authorization checks backed by user-service effective permission assignments.

Every user-service permission/access-grant lookup this service makes goes
through :class:`AuthorizationClient` — RBAC-style permission strings
(``has_permission``/``is_admin``) and resource-grant checks for individual
collections (``check_collection_access``/``get_user_accessible_collections``)
alike. They used to be split across two independently-implemented HTTP
clients (this one, and a since-removed ``services.permission_service``) with
different pooling and header-building; keeping them in one place means one
client pattern, one header helper, and cleanup handled once by
``security.close_all()`` at shutdown.
"""

from __future__ import annotations

import time
from typing import Any

from cachetools import LRUCache
from config_manager import env
from error_contract import (
    ApplicationError,
    DependencyResponseError,
    from_httpx_error,
)
import httpx
from localization import get_locale
from security import get_shared_client

from src.shared.api_versioning import USER_SERVICE_API_PREFIX
from src.shared.observability import get_logger
from src.shared.user_response import read_user_response

logger = get_logger(__name__)

HTTP_OK = 200

#: The pooled client carries a longer default read timeout than these calls
#: want: an authorization lookup sits on the request hot path, so it is held
#: to the same 5 seconds it used before, per request rather than per client.
_REQUEST_TIMEOUT_SECONDS = 5.0


class AuthorizationClient:
    """User-service authorization client with a process-local decision cache."""

    def __init__(self) -> None:
        """Initialize the process-local permission decision cache.

        Bounded: an unbounded dict here grew one entry per (user,
        permission) pair ever checked, for the lifetime of the process.
        """
        self._permission_cache: LRUCache[tuple[str, str], tuple[bool, float]] = LRUCache(maxsize=10_000)

    async def check_collection_access(
        self,
        user_id: str,
        collection_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        """Check whether a user has a specific grant on a RAG collection.

        Returns ``{"allowed": bool, "permission_level": str | None, "source": str | None}``.
        User-service failures propagate through the shared dependency error
        contract so callers can distinguish an outage from an explicit denial.
        """
        try:
            response = await get_shared_client("user-service").post(
                f"{env.INTERNAL_USER_SERVICE_URL.rstrip('/')}{USER_SERVICE_API_PREFIX}/permissions/check",
                json={
                    "user_id": str(user_id),
                    "resource_type": "rag_collection",
                    "resource_id": str(collection_id),
                    "required_permission": required_permission,
                },
                headers=self._user_service_headers(None),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            data = read_user_response(response)
            if not isinstance(data, dict) or not isinstance(data.get("allowed"), bool):
                raise DependencyResponseError
            return data
        except httpx.TimeoutException as exc:
            raise from_httpx_error(exc) from exc
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise from_httpx_error(exc) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DependencyResponseError from exc

    async def get_user_accessible_collections(self, user_id: str) -> list[str]:
        """Return the ids of every RAG collection this user has read access to."""
        try:
            response = await get_shared_client("user-service").get(
                f"{env.INTERNAL_USER_SERVICE_URL.rstrip('/')}"
                f"{USER_SERVICE_API_PREFIX}/permissions/users/{user_id}/accessible-resources",
                params={
                    "resource_type": "rag_collection",
                    "required_permission": "read",
                },
                headers=self._user_service_headers(None),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            data = read_user_response(response)
            if not isinstance(data, dict) or not isinstance(data.get("resources", []), list):
                raise DependencyResponseError
            resources = data.get("resources", [])
            if any(not isinstance(resource, dict) or "resource_id" not in resource for resource in resources):
                raise DependencyResponseError
            return [r["resource_id"] for r in resources]
        except httpx.TimeoutException as exc:
            raise from_httpx_error(exc) from exc
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise from_httpx_error(exc) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DependencyResponseError from exc

    async def is_admin(self, user_id: str, access_token: str | None = None) -> bool:
        """Resolve authoritative system or enterprise administrator status."""
        try:
            response = await get_shared_client("user-service").get(
                f"{env.INTERNAL_USER_SERVICE_URL.rstrip('/')}"
                f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/permissions",
                headers=self._user_service_headers(access_token),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            data = read_user_response(response)
            return isinstance(data, dict) and data.get("is_admin") is True
        except (httpx.HTTPError, ValueError, ApplicationError):
            return False

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
            now + env.USER_PERMISSION_CACHE_TTL_SECONDS,
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
            response = await get_shared_client("user-service").post(
                (f"{env.INTERNAL_USER_SERVICE_URL.rstrip('/')}{USER_SERVICE_API_PREFIX}/internal/users/authorize"),
                headers=headers,
                json={"target_id": user_id, "permission": permission},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == HTTP_OK:
                data = read_user_response(response)
                return bool(data.get("allowed")) if isinstance(data, dict) else False
        except (httpx.HTTPError, ValueError, ApplicationError):
            pass

        return await self._fallback_to_effective_permissions(
            user_id=user_id,
            permission=permission,
            headers=headers,
        )

    @staticmethod
    def _user_service_headers(access_token: str | None) -> dict[str, str]:
        headers: dict[str, str] = {"X-Language": get_locale()}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        internal_token = env.INTERNAL_SERVICE_TOKEN.strip()
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
            response = await get_shared_client("user-service").get(
                (
                    f"{env.INTERNAL_USER_SERVICE_URL.rstrip('/')}"
                    f"{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/permissions"
                ),
                headers=headers,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != HTTP_OK:
                return False
            data = read_user_response(response)
        except (httpx.HTTPError, ValueError, ApplicationError):
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
