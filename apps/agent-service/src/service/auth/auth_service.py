"""
Authentication helpers.

Agent-service does not authenticate anyone. Gateway introspects the user token
with Keycloak, applies the route's authorization decision, and forwards the
result as trusted headers; this module turns that identity into user context and
resolves the user-service view of it.

The FastAPI HTTP dependencies (``require_user``, ``require_permission``, …) live
in ``api.dependencies``; import them from there.
"""

from dataclasses import dataclass, field
from typing import Any

from security import GatewayIdentity

from core.exceptions import ApplicationError
from core.observability.logger import get_logger
from integrations.user_service_client import (
    get_current_user as get_user_service_current_user,
)

__all__ = [
    "AuthService",
    "AuthenticatedUser",
    "get_auth_service",
    "get_primary_user_id",
    "resolve_known_user_ids",
]

logger = get_logger(__name__)

_auth_service: "AuthService | None" = None


# ---------------------------------------------------------------------------
# AuthenticatedUser — typed result of successful token validation
# ---------------------------------------------------------------------------


@dataclass
class AuthenticatedUser:
    user_id: str
    email: str
    username: str | None = None
    roles: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    access_token: str | None = None


# ---------------------------------------------------------------------------
# AuthService — user context resolution over the identity Gateway established
# ---------------------------------------------------------------------------


class AuthService:
    """User context resolution for agent-service.

    Authentication happens at Gateway. Nothing here contacts Keycloak.
    """

    @staticmethod
    def _extract_roles(claims: dict[str, Any]) -> list[str]:
        roles: set[str] = set()

        direct_role = claims.get("role")
        if isinstance(direct_role, str):
            roles.add(direct_role.lower())
        direct_roles = claims.get("roles")
        if isinstance(direct_roles, list):
            roles.update(str(r).lower() for r in direct_roles)

        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            r = realm_access.get("roles") or []
            if isinstance(r, list):
                roles.update(str(x).lower() for x in r)

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            for client_data in resource_access.values():
                if isinstance(client_data, dict):
                    r = client_data.get("roles") or []
                    if isinstance(r, list):
                        roles.update(str(x).lower() for x in r)

        return sorted(roles)

    @staticmethod
    def _extract_permissions(claims: dict[str, Any]) -> set[str]:
        permissions: set[str] = set()

        direct_permissions = claims.get("permissions")
        if isinstance(direct_permissions, list):
            permissions.update(str(p) for p in direct_permissions if p is not None)
        elif isinstance(direct_permissions, str):
            permissions.add(direct_permissions)

        return permissions

    @staticmethod
    def has_permission(claims: dict[str, Any], permission: str) -> bool:
        permissions = AuthService._extract_permissions(claims)
        return "*" in permissions or permission in permissions

    @staticmethod
    def build_authenticated_user(
        claims: dict[str, Any],
        access_token: str | None = None,
    ) -> AuthenticatedUser:
        user_id = str(claims.get("sub") or claims.get("preferred_username") or claims.get("email") or "unknown")
        email = claims.get("email") or claims.get("preferred_username") or f"{user_id}@local.dev"
        username = claims.get("preferred_username") or claims.get("email", "").split("@")[0]
        roles = AuthService._extract_roles(claims)

        return AuthenticatedUser(
            user_id=user_id,
            email=str(email),
            username=str(username) if username else None,
            roles=roles,
            claims=claims,
            access_token=access_token,
        )

    @staticmethod
    def build_authenticated_user_from_user_service(
        user_data: dict[str, Any],
        access_token: str | None = None,
    ) -> AuthenticatedUser:
        user_id = str(user_data.get("id") or user_data.get("sub") or "unknown")
        email = str(user_data.get("email") or f"{user_id}@local.dev")
        username = user_data.get("username")
        role = user_data.get("role")
        roles = [str(role).lower()] if role else []

        claims = {
            "sub": user_id,
            "email": email,
            "preferred_username": username,
            "role": role,
            "type": "access",
            "user_service_user": user_data,
        }
        if user_data.get("keycloak_id"):
            claims["keycloak_id"] = user_data["keycloak_id"]

        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            username=str(username) if username else None,
            roles=roles,
            claims=claims,
            access_token=access_token,
        )

    @staticmethod
    def build_authenticated_user_from_gateway(
        identity: GatewayIdentity,
        access_token: str | None = None,
    ) -> AuthenticatedUser:
        """Build user context from the identity Gateway already authenticated."""
        user_id = identity.user_id
        email = identity.email or f"{user_id}@local.dev"
        username = identity.username
        if not username and "@" in email:
            username = email.split("@", 1)[0]

        claims: dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "preferred_username": username,
            "type": "access",
            "gateway_authenticated": True,
        }
        if identity.roles:
            claims["realm_access"] = {"roles": list(identity.roles)}
        if identity.delegated_user_id:
            claims["delegated_user_id"] = identity.delegated_user_id

        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            username=str(username) if username else None,
            roles=list(identity.roles),
            claims=claims,
            access_token=access_token,
        )

    @staticmethod
    async def authenticate_with_user_service(token: str) -> AuthenticatedUser | None:
        try:
            user_data = await get_user_service_current_user(token)
        except ApplicationError as exc:
            if exc.status_code in {401, 403, 404}:
                return None
            raise
        if not user_data:
            return None
        return AuthService.build_authenticated_user_from_user_service(user_data, token)

    async def resolve_user_identity(
        self,
        token: str | None,
        user_id: str | None,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        user_service_user = None
        keycloak_id = user.claims.get("keycloak_id") if user else None
        if user and isinstance(user.claims.get("user_service_user"), dict):
            user_service_user = user.claims["user_service_user"]

        if not keycloak_id and user:
            # Gateway already resolved the subject; user_id is the Keycloak sub.
            keycloak_id = user.user_id

        if not keycloak_id:
            keycloak_id = user_id

        if not user_service_user and keycloak_id:
            try:
                from integrations.user_service_client import get_user_by_keycloak_id

                user_service_user = await get_user_by_keycloak_id(str(keycloak_id), token)
            except Exception as exc:
                logger.warning("Failed to resolve user identity from user-service: %s", exc)

        primary_user_id = None
        if isinstance(user_service_user, dict) and user_service_user.get("id"):
            primary_user_id = str(user_service_user["id"])
        elif user_id:
            primary_user_id = str(user_id)

        known_user_ids: list[str] = []
        for candidate in (primary_user_id, keycloak_id, user_id):
            if not candidate:
                continue
            normalized = str(candidate)
            if normalized not in known_user_ids:
                known_user_ids.append(normalized)

        return {
            "primary_user_id": primary_user_id,
            "keycloak_id": str(keycloak_id) if keycloak_id else None,
            "user_service_user": user_service_user,
            "known_user_ids": known_user_ids,
        }


def get_primary_user_id(identity: dict[str, Any] | None, fallback_user_id: str | None) -> str | None:
    """Pick the id that owns a request: the resolved identity's, else the caller's.

    Pure and transport-free, so the service layer can call it without reaching
    into the API layer for a request object.
    """
    if identity and identity.get("primary_user_id"):
        return str(identity["primary_user_id"])
    if fallback_user_id:
        return str(fallback_user_id)
    return None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


# ------------------------------------------------------------------
# Module-level identity helpers
#
# The FastAPI dependencies themselves moved to ``api.dependencies`` (see the
# shim above). These two stay here: they are plain identity resolution over
# ``AuthService``, called from services and domain code that must not import
# the HTTP dependency layer.
# ------------------------------------------------------------------


def resolve_user_service_id(user: AuthenticatedUser) -> str | None:
    """The user-service `users.id` for this authenticated user, if known.

    Fine-grained permission checks and audit records (P3 Task 19) both need
    a real user-service UUID rather than whatever identifier happened to
    authenticate the request — a Keycloak `sub`, an API key, or the literal
    "dev-user". Returns None when no such id is available; callers decide
    their own fallback (the flow audit emitter records the raw identifier in
    event details instead of guessing a FK-safe value).
    """
    user_service_user = user.claims.get("user_service_user")
    if isinstance(user_service_user, dict) and user_service_user.get("id"):
        return str(user_service_user["id"])
    return None


async def resolve_known_user_ids(
    user_id: str | None,
    *,
    token: str | None = None,
    user: AuthenticatedUser | None = None,
) -> list[str]:
    """Owner-id candidates for ``user_id``, bridging Keycloak ``sub`` vs user-service id.

    Rows owned by a user may be stored under either identifier (personas use the
    user-service primary id, mail configs use the Keycloak ``sub``). Delegates to
    :meth:`AuthService.resolve_user_identity` — which already logs user-service
    failures — and always includes the raw ``user_id`` so a lookup stays scoped
    to the caller even when user-service is unreachable. Returns ``[]`` only when
    ``user_id`` itself is blank, so callers never fall back to an unscoped query.
    """
    if not user_id:
        return []
    raw = str(user_id)
    try:
        identity = await get_auth_service().resolve_user_identity(token=token, user_id=raw, user=user)
        known = [str(candidate) for candidate in identity.get("known_user_ids") or [] if candidate]
    except Exception as exc:
        logger.warning("Failed to resolve known user ids for %s: %s", raw, exc)
        known = []
    if raw not in known:
        known.append(raw)
    return known
