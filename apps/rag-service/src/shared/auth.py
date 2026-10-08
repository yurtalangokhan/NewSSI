# Copyright (c) 2026 Agentic AI Platform
"""Caller identity resolved from the headers Gateway sets.

RAG-service does not authenticate anyone. Gateway introspects the user token
with Keycloak, applies the route's authorization decision, and forwards the
result as trusted headers. This module turns those headers into a user; it never
validates a token itself and has no API-key or development path.
"""

from __future__ import annotations

from typing import Annotated, Any

from config_manager import env
from error_contract import ForbiddenError, UnauthorizedError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.authentication import BaseUser

from src.shared.gateway_identity import (
    INTERNAL_SERVICE_USER_ID,
    resolve_gateway_identity,
)

security = HTTPBearer(auto_error=False)
HTTP_OK = 200

# Shared secret proving a request traversed Gateway.
INTERNAL_SERVICE_TOKEN = env.INTERNAL_SERVICE_TOKEN


class AuthenticatedUser(BaseUser):
    """An authenticated user following the Starlette authentication model."""

    def __init__(
        self,
        user_id: str,
        display_name: str,
        access_token: str | None = None,
        claims: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the AuthenticatedUser.

        Args:
            user_id: Unique identifier for the user.
            display_name: Display name for the user.
            access_token: User bearer token used for downstream permission checks.
            claims: Decoded JWT claims used for permission checks.
        """
        self.user_id = user_id
        self._display_name = display_name
        self.access_token = access_token
        self.claims = claims or {}

    @property
    def is_authenticated(self) -> bool:
        """Return True if the user is authenticated."""
        return True

    @property
    def display_name(self) -> str:
        """Return the display name of the user."""
        return self._display_name

    @property
    def identity(self) -> str:
        """Return the identity of the user. This is a unique identifier."""
        return self.user_id


def _extract_auth_token(
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """The bearer token Gateway forwarded, for downstream user-service calls.

    Never trusted for authentication; only passed on so user-service can resolve
    permissions for the same principal.
    """
    if credentials and credentials.credentials:
        candidate = credentials.credentials.strip()
        if candidate and candidate != (INTERNAL_SERVICE_TOKEN or "").strip():
            return candidate

    return None


def _claim_permissions(claims: dict[str, Any]) -> set[str]:
    permissions: set[str] = set()

    direct_permissions = claims.get("permissions")
    if isinstance(direct_permissions, list):
        permissions.update(str(p) for p in direct_permissions if p is not None)
    elif isinstance(direct_permissions, str):
        permissions.add(direct_permissions)

    client_id = env.KEYCLOAK_CLIENT_ID
    resource_access = claims.get("resource_access")
    if isinstance(resource_access, dict):
        client_mapping = resource_access.get(client_id)
        if isinstance(client_mapping, dict):
            client_roles = client_mapping.get("roles") or []
            if isinstance(client_roles, list):
                permissions.update(str(role) for role in client_roles if role is not None)

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles") or []
        if isinstance(realm_roles, list):
            permissions.update(str(role) for role in realm_roles if role is not None)

    return permissions


def _claims_have_permission(claims: dict[str, Any], permission: str) -> bool:
    permissions = _claim_permissions(claims)
    return "*" in permissions or permission in permissions


async def resolve_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
) -> AuthenticatedUser:
    """Return the caller Gateway authenticated.

    Raises 401 when the request did not arrive through Gateway with a trusted
    identity. There is no anonymous, API-key or development fallback.
    """
    if credentials and credentials.scheme != "Bearer":
        raise UnauthorizedError(code="auth.invalid_scheme", message_key="errors.rag.auth.invalid_scheme")

    identity = resolve_gateway_identity(request.headers, INTERNAL_SERVICE_TOKEN)
    if identity is None:
        raise UnauthorizedError(message_key="errors.rag.auth.bearer_token_required")

    if identity.is_internal:
        return AuthenticatedUser(INTERNAL_SERVICE_USER_ID, "Internal Service")

    token = _extract_auth_token(credentials)
    display_name = identity.email or identity.username or identity.user_id
    claims: dict[str, Any] = {
        "sub": identity.user_id,
        "email": identity.email,
        "preferred_username": identity.username,
        "realm_access": {"roles": list(identity.roles)},
    }
    return AuthenticatedUser(
        identity.user_id,
        display_name,
        access_token=token,
        claims=claims,
    )


def require_permission(permission: str):
    """Factory returning a FastAPI dependency that authenticates and checks a permission.

    Usage: ``user = Depends(require_permission("collection:create"))``

    Authenticates via resolve_user, then calls user-service to verify the user's
    role includes the required permission. Internal-service callers bypass.

    Fine-grained permissions live ONLY in the user-service database, not in the
    JWT. The JWT contains only coarse client roles for service-level grouping.
    """

    async def _check(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    ) -> AuthenticatedUser:
        user = await resolve_user(request=request, credentials=credentials)

        if user.identity == INTERNAL_SERVICE_USER_ID:
            return user

        from src.shared.authorization import (
            get_authorization_client,
        )

        if await get_authorization_client().has_permission(
            user.identity,
            permission,
            user.access_token,
        ):
            return user

        raise ForbiddenError(
            code="auth.permission_required",
            message_key="errors.rag.auth.permission_required",
            message_params={"permission": permission},
        )

    return _check
