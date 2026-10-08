"""Authorization data fetched from user-service for MCP token scopes."""

from __future__ import annotations

from dataclasses import dataclass
import time

from cachetools import LRUCache
from config_manager import env
from error_contract import ApplicationError
import httpx
from localization import get_locale

from .api_versioning import USER_SERVICE_API_PREFIX
from .observability import get_logger
from .user_response import read_user_response

logger = get_logger(__name__)

# Bounded: an unbounded dict here grew one entry per subject ever
# authorized, for the lifetime of the process. Expiry stays a manual
# (expires_at, permissions) check below since the TTL is a runtime
# setting, not a fixed value a cachetools.TTLCache could be built with.
_PERMISSION_CACHE: LRUCache[str, tuple[float, list[str]]] = LRUCache(maxsize=10_000)


def _user_service_base_url() -> str:
    return env.INTERNAL_USER_SERVICE_URL


def _permission_cache_ttl() -> float:
    return env.USER_PERMISSION_CACHE_TTL_SECONDS


def _user_service_headers(token: str) -> dict[str, str]:
    settings = env
    headers = {"Authorization": f"Bearer {token}", "X-Language": get_locale()}
    internal_token = settings.INTERNAL_SERVICE_TOKEN.strip()
    if internal_token:
        headers["X-Internal-Service-Token"] = internal_token
    return headers


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
                headers=_user_service_headers(token),
            )
        data = read_user_response(resp)
    except (httpx.HTTPError, ValueError, ApplicationError):
        return []

    raw_permissions = data.get("permissions", []) if isinstance(data, dict) else []
    permissions = sorted(str(permission) for permission in raw_permissions if permission is not None)
    _PERMISSION_CACHE[subject] = (now + _permission_cache_ttl(), permissions)
    return permissions


@dataclass(frozen=True)
class BindingAuthorizationResult:
    authorized: bool
    reason: str | None = None


async def authorize_binding_reference(
    binding_type: str,
    binding_id: str,
    user_id: str | None,
    tenant_id: str | None,
    internal_token: str,
) -> BindingAuthorizationResult:
    """Verify the user/tenant owns a binding reference for a given type.

    The user-service ``/internal/{tenant}/bindings/{type}/{id}/access`` endpoint
    is called to confirm access. Returns ``authorized=True`` if the service
    confirms the binding is accessible. User-service errors fail closed because
    binding references gate access to credentials and other trusted resources.
    """
    if not user_id and not tenant_id:
        return BindingAuthorizationResult(
            authorized=False,
            reason="No user_id or tenant_id in trusted context.",
        )

    base = _user_service_base_url().rstrip("/")
    if tenant_id:
        path = f"{base}{USER_SERVICE_API_PREFIX}/internal/{tenant_id}/bindings/{binding_type}/{binding_id}/access"
    else:
        path = f"{base}{USER_SERVICE_API_PREFIX}/internal/users/{user_id}/bindings/{binding_type}/{binding_id}/access"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                path,
                headers=_user_service_headers(internal_token),
            )
        if resp.status_code == 204:
            return BindingAuthorizationResult(authorized=True)
        if resp.status_code == 200:
            data = read_user_response(resp)
            return BindingAuthorizationResult(
                authorized=isinstance(data, dict) and data.get("allowed") is True,
                reason=None
                if isinstance(data, dict) and data.get("allowed") is True
                else "Binding access was not explicitly granted.",
            )
        elif resp.status_code == 403:
            return BindingAuthorizationResult(
                authorized=False,
                reason=f"Access denied for {binding_type}/{binding_id}",
            )
        else:
            logger.warning(
                "Unexpected status %s from binding authorization: %s",
                resp.status_code,
                path,
            )
            return BindingAuthorizationResult(
                authorized=False,
                reason="Authorization check returned unexpected status.",
            )
    except (httpx.HTTPError, ApplicationError) as exc:
        logger.warning(
            "Binding authorization unavailable, failing closed: %s — %s",
            path,
            exc,
        )
        return BindingAuthorizationResult(
            authorized=False,
            reason="Authorization check unavailable.",
        )


async def authorize_all_bindings(
    binding_references: dict[str, str],
    user_id: str | None,
    tenant_id: str | None,
    internal_token: str,
) -> dict[str, BindingAuthorizationResult]:
    """Run authorization for all binding references in the trusted context.

    Returns a dict of ``binding_type -> BindingAuthorizationResult``.
    """
    results: dict[str, BindingAuthorizationResult] = {}
    for binding_type, binding_id in binding_references.items():
        results[binding_type] = await authorize_binding_reference(
            binding_type=binding_type,
            binding_id=binding_id,
            user_id=user_id,
            tenant_id=tenant_id,
            internal_token=internal_token,
        )
    return results
