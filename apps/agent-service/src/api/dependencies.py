"""API dependencies - shared FastAPI dependencies.

This module lives at the API boundary. It owns the HTTP-framework concerns
(``Request``, ``Depends``) and turns the trusted headers Gateway sets into an
``AuthenticatedUser``.

Agent-service does not verify user tokens. Gateway introspects the token with
Keycloak and applies the route's authorization decision before forwarding, so a
request that arrives here has already been authenticated. Identity comes from
``security.gateway``; fine-grained permissions still resolve through
user-service in :func:`require_permission`.

These dependencies live here rather than in ``service.auth``: they are HTTP
concerns (``Request``/``Depends``), and the service layer must not import them.
"""

from config_manager import env
from fastapi import Depends, Request
from localization import t
from security import (
    INTERNAL_SERVICE_USER_ID,
    GatewayIdentity,
    resolve_gateway_identity,
)

from core.exceptions import ForbiddenError, UnauthorizedError
from core.observability.logger import get_logger
from integrations.user_service_client import get_current_access_token, set_current_access_token
from service.auth.auth_service import AuthenticatedUser, AuthService, get_primary_user_id

logger = get_logger(__name__)


def _extract_auth_token(request: Request) -> str | None:
    """The bearer token Gateway forwarded, for downstream user-service calls.

    This value is never trusted for authentication. It is passed on so
    user-service can resolve permissions for the same principal.
    """
    header = (request.headers.get("Authorization") or "").strip()
    if header.lower().startswith("bearer "):
        candidate = header[7:].strip()
        if candidate and candidate != (env.INTERNAL_SERVICE_TOKEN or "").strip():
            return candidate
    return None


def extract_auth_token_from_request(request: Request) -> str | None:
    """Extract the forwarded bearer token from a request."""
    return get_current_access_token() or _extract_auth_token(request)


def _resolve_identity(request: Request) -> GatewayIdentity | None:
    return resolve_gateway_identity(request.headers, env.INTERNAL_SERVICE_TOKEN)


async def require_user(request: Request) -> AuthenticatedUser:
    """Return the caller Gateway authenticated.

    Raises UnauthorizedError when the request did not arrive through Gateway
    with a trusted identity.
    """
    identity = _resolve_identity(request)
    if identity is None:
        raise UnauthorizedError(message=t("auth.missing_bearer_token"))

    token = None if identity.is_internal else _extract_auth_token(request)
    set_current_access_token(token)
    return AuthService.build_authenticated_user_from_gateway(identity, token)


async def has_permission(user: AuthenticatedUser, permission: str) -> bool:
    """Does ``user`` hold ``permission``? Internal-service callers hold every one.

    Fine-grained permissions live ONLY in user-service, not in the JWT.
    """
    if user.user_id == INTERNAL_SERVICE_USER_ID:
        return True

    from service.auth.auth_service import get_auth_service

    # Resolve application identity before checking resource permissions.
    identity = await get_auth_service().resolve_user_identity(
        token=user.access_token, user_id=user.user_id, user=user
    )
    permission_user_id = identity.get("primary_user_id") or user.user_id

    from integrations.authorization_client import get_authorization_client

    return await get_authorization_client().has_permission(
        permission_user_id,
        permission,
        user.access_token,
    )


def require_permission(permission: str):
    """Factory returning a FastAPI dependency requiring a specific permission.

    Usage: ``user = Depends(require_permission("datasource:create"))``

    Authenticates via require_user, then fetches the user's resolved permissions
    from user-service (the source of truth) and verifies membership.
    Internal-service callers bypass.

    Fine-grained permissions live ONLY in user-service, not in the JWT. Gateway
    authorizes the route; this protects the resource-level operation.
    """

    async def _check_permission(
        user: AuthenticatedUser = Depends(require_user),
    ) -> AuthenticatedUser:
        if await has_permission(user, permission):
            return user

        raise ForbiddenError(
            message=t("auth.missing_permission", permission=permission),
        )

    return _check_permission


async def require_user_or_internal_service_token(request: Request) -> AuthenticatedUser:
    """Alias of :func:`require_user`.

    Gateway identity already covers both the user and the machine caller, so
    this exists only for call sites that document the internal path explicitly.
    """
    return await require_user(request)


def verify_bearer(request: Request) -> None:
    """Reject a request that did not arrive through Gateway."""
    if _resolve_identity(request) is None:
        raise UnauthorizedError(message=t("auth.missing_bearer_token"))


def verify_bearer_or_internal_service_token(request: Request) -> None:
    """Alias of :func:`verify_bearer`; internal callers are covered by it."""
    verify_bearer(request)


def verify_api_key(request: Request) -> str | None:
    """Return the caller's id when Gateway authenticated it, else None."""
    identity = _resolve_identity(request)
    return identity.user_id if identity else None


def require_internal_service_identity(request: Request) -> str:
    """Validate internal service token and return the associated user ID.

    Used by internal service-to-service endpoints like connector tool execution.
    """
    import secrets

    from fastapi import HTTPException

    expected = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    supplied = request.headers.get("x-internal-service-token", "")
    user_id = request.headers.get("x-user-id", "").strip()
    if not expected or not secrets.compare_digest(expected, supplied) or not user_id or user_id == "internal-service":
        raise HTTPException(
            status_code=403,
            detail=t("connectors.internal_required", default="Trusted internal identity is required."),
        )
    return user_id


__all__ = [
    "AuthenticatedUser",
    "extract_auth_token_from_request",
    "get_primary_user_id",
    "has_permission",
    "require_internal_service_identity",
    "require_permission",
    "require_user",
    "require_user_or_internal_service_token",
    "verify_api_key",
    "verify_bearer",
    "verify_bearer_or_internal_service_token",
]
