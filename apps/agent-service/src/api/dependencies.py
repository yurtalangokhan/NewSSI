"""API dependencies - shared FastAPI dependencies.

This module lives at the API boundary. It owns the HTTP-framework concerns
(``Request``, ``HTTPBearer``, ``Depends``) and delegates token validation and
user-profile resolution to the pure domain logic in ``service.AuthService``.

The functions here are re-exported from ``service.AuthService`` as a documented
backward-compatibility shim, so existing ``from service.AuthService import
require_user`` imports continue to work.
"""

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from i18n import t

from core.exceptions import (
    ApplicationError,
    ForbiddenError,
    UnauthorizedError,
)
from core.logger import get_logger
from core.settings import settings
from service.AuthService import (
    AuthenticatedUser,
    AuthService,
)
from service.UserServiceClient import (
    set_current_access_token,
)

logger = get_logger(__name__)


def _get_valid_api_keys() -> set:
    keys = settings.VALID_API_KEYS
    if keys:
        return set(k.strip() for k in keys.split(",") if k.strip())
    return set()


def _extract_auth_token(
    http_auth: HTTPAuthorizationCredentials | None,
    request: Request,
) -> str | None:
    if http_auth and http_auth.credentials:
        return http_auth.credentials
    return (
        request.cookies.get("fastapiusersauth")
        or request.cookies.get("session")
        or request.cookies.get("access_token")
        or request.cookies.get("id_token")
    )


def _extract_auth_tokens(
    http_auth: HTTPAuthorizationCredentials | None,
    request: Request,
) -> list[str]:
    tokens: list[str] = []
    if http_auth and http_auth.credentials:
        tokens.append(http_auth.credentials)
    for cookie_name in ("fastapiusersauth", "session", "access_token", "id_token"):
        token = request.cookies.get(cookie_name)
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def extract_auth_token_from_request(request: Request) -> str | None:
    """Extract the bearer/cookie token from a request (no HTTP auth object)."""
    return _extract_auth_token(None, request)


def _is_keycloak_enabled() -> bool:
    return AuthService.is_keycloak_enabled()


def _decode_keycloak_token(token: str) -> dict:
    return AuthService.decode_keycloak_token(token)


def extract_user_id_from_token(token: str) -> str | None:
    return AuthService.extract_user_id_from_token(token)


def get_primary_user_id(
    identity: dict[str, Any] | None, fallback_user_id: str | None
) -> str | None:
    if identity and identity.get("primary_user_id"):
        return str(identity["primary_user_id"])
    if fallback_user_id:
        return str(fallback_user_id)
    return None


def _has_valid_internal_service_token(request: Request) -> bool:
    internal_token = (settings.INTERNAL_SERVICE_TOKEN or "").strip()
    if not internal_token:
        return False

    header_token = (request.headers.get("X-Internal-Service-Token") or "").strip()
    if header_token == internal_token:
        return True

    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() == internal_token

    return False


def _internal_service_user(token: str | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="internal-service",
        email="internal@service.local",
        roles=["internal"],
        access_token=token,
    )


async def require_user(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> AuthenticatedUser:
    """Validate bearer token and return authenticated user context.

    Raises UnauthorizedError if token is missing or invalid.
    """
    token = _extract_auth_token(http_auth, request)
    set_current_access_token(token)

    if _is_keycloak_enabled():
        if not token:
            raise UnauthorizedError(
                message=t("auth.missing_bearer_token"),
            )
        try:
            claims = _decode_keycloak_token(token)
            return AuthService.build_authenticated_user(claims, token)
        except ApplicationError:
            user = await AuthService.authenticate_with_user_service(token)
            if user:
                return user
            raise

    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        # No keys configured — dev mode, allow all
        return AuthenticatedUser(user_id="dev-user", email="dev@local.dev")

    if not token:
        raise UnauthorizedError(
            message=t("auth.missing_bearer_token"),
        )

    if token in valid_keys:
        uid = extract_user_id_from_token(token)
        return AuthenticatedUser(
            user_id=uid or token,
            email=f"{uid or token}@local.dev",
            access_token=token,
        )

    uid = extract_user_id_from_token(token)
    if uid in valid_keys:
        return AuthenticatedUser(
            user_id=uid,
            email=f"{uid}@local.dev",
            access_token=token,
        )

    raise UnauthorizedError(
        message=t("auth.invalid_bearer_token"),
    )


def require_permission(permission: str):
    """Factory returning a FastAPI dependency requiring a specific permission.

    Usage: ``user = Depends(require_permission("datasource:create"))``

    Authenticates via require_user, then fetches the user's resolved permissions
    from user-service (the source of truth) and verifies membership.
    Dev mode and internal-service bypass.

    Fine-grained permissions live ONLY in the user-service database, not in the
    JWT. The JWT contains only coarse client roles for service-level grouping.
    """

    async def _check_permission(
        user: AuthenticatedUser = Depends(require_user),
    ) -> AuthenticatedUser:
        if user.user_id in ("dev-user", "internal-service"):
            return user

        user_service_user = user.claims.get("user_service_user")
        permission_user_id = (
            str(user_service_user["id"])
            if isinstance(user_service_user, dict) and user_service_user.get("id")
            else user.user_id
        )

        from service.AuthorizationClient import get_authorization_client

        if await get_authorization_client().has_permission(
            permission_user_id,
            permission,
            user.access_token,
        ):
            return user

        raise ForbiddenError(
            message=t("auth.missing_permission", permission=permission),
        )

    return _check_permission


async def require_user_or_internal_service_token(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> AuthenticatedUser:
    """Like require_user, but also accepts the INTERNAL_SERVICE_TOKEN header."""
    if _has_valid_internal_service_token(request):
        return _internal_service_user(settings.INTERNAL_SERVICE_TOKEN)

    return await require_user(request=request, http_auth=http_auth)


def verify_bearer(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> None:
    """Deprecated: use require_user instead."""
    token = _extract_auth_token(http_auth, request)

    if _is_keycloak_enabled():
        if not token:
            raise UnauthorizedError(
                message=t("auth.missing_bearer_token"),
            )
        _decode_keycloak_token(token)
        return

    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return

    if token:
        if token in valid_keys:
            return
        uid = extract_user_id_from_token(token)
        if uid in valid_keys:
            return

    raise UnauthorizedError(
        message=t("auth.invalid_bearer_token"),
    )


def verify_api_key(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide API key", auto_error=False)),
    ],
) -> str | None:
    """Deprecated: use require_user instead."""
    if _is_keycloak_enabled():
        candidate_tokens = _extract_auth_tokens(http_auth, request)
        if not candidate_tokens:
            return None
        for token in candidate_tokens:
            try:
                claims = _decode_keycloak_token(token)
                return claims.get("sub") or claims.get("preferred_username") or claims.get("email")
            except ApplicationError:
                continue
        raise UnauthorizedError(
            message=t("auth.invalid_bearer_token"),
        )

    token = _extract_auth_token(http_auth, request)
    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return "dev-user"
    if not token:
        return None
    if token in valid_keys:
        return extract_user_id_from_token(token)
    uid = extract_user_id_from_token(token)
    if uid in valid_keys:
        return uid
    raise UnauthorizedError(
        message=t("auth.invalid_api_key"),
    )


def verify_bearer_or_internal_service_token(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> None:
    """Deprecated: use require_user_or_internal_service_token instead."""
    if _has_valid_internal_service_token(request):
        return

    verify_bearer(request=request, http_auth=http_auth)


__all__ = [
    "AuthenticatedUser",
    "require_permission",
    "require_user",
    "require_user_or_internal_service_token",
    "verify_bearer",
    "verify_api_key",
    "extract_user_id_from_token",
    "extract_auth_token_from_request",
    "get_primary_user_id",
]
