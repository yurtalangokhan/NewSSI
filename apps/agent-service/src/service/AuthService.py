"""
Authentication helpers.

Agent-service does not issue, refresh, or revoke user tokens. User-service owns
login, logout, registration, and OIDC flows. This module only validates incoming
tokens and resolves user context for protected agent-service endpoints.

This module contains the pure domain logic (token decode, claims extraction,
user-profile building). The FastAPI HTTP dependencies (``require_user``,
``require_permission``, etc.) live in ``api.dependencies`` and are re-exported
here as a documented backward-compatibility shim. The Keycloak admin client
lives in ``integrations.keycloak_admin``.
"""

from dataclasses import dataclass, field
from typing import Any

import jwt
from i18n import t
from jwt import InvalidTokenError, PyJWKClient

from core.exceptions import (
    ApplicationError,
    DependencyUnavailableError,
    UnauthorizedError,
)
from core.logger import get_logger
from core.settings import settings
from integrations.keycloak_admin import get_keycloak_user_profile
from service.UserServiceClient import (
    get_current_user as get_user_service_current_user,
)
from service.UserServiceClient import (
    get_user_settings,
)

__all__ = [  # noqa: F822  (FastAPI deps resolved lazily via __getattr__ shim)
    "AuthService",
    "get_auth_service",
    "AuthenticatedUser",
    "require_user",
    "require_permission",
    "require_user_or_internal_service_token",
    "get_primary_user_id",
    "resolve_known_user_ids",
    "verify_bearer",
    "verify_bearer_or_internal_service_token",
    "extract_user_id_from_token",
    "verify_api_key",
]

# Symbols moved to their proper layers (documented backward-compatibility shim):
# - FastAPI dependencies -> api.dependencies
# These are resolved lazily via __getattr__ below to avoid a circular import
# (api.dependencies imports AuthService from this module).
_SHIM_SOURCES = {
    "require_user": "api.dependencies",
    "require_permission": "api.dependencies",
    "require_user_or_internal_service_token": "api.dependencies",
    "verify_bearer": "api.dependencies",
    "verify_api_key": "api.dependencies",
    "verify_bearer_or_internal_service_token": "api.dependencies",
    "extract_user_id_from_token": "api.dependencies",
    "get_primary_user_id": "api.dependencies",
    "extract_auth_token_from_request": "api.dependencies",
    "get_keycloak_admin_token": "integrations.keycloak_admin",
}


def __getattr__(name: str):
    module_name = _SHIM_SOURCES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


logger = get_logger(__name__)

_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_KEYS: dict[str, Any] = {}  # kid -> key cache
_auth_service: "AuthService | None" = None


def _refresh_jwks() -> None:
    """Reset the JWKS client cache so the next lookup re-fetches keys."""
    global _JWKS_CLIENT, _JWKS_KEYS
    _JWKS_CLIENT = None
    _JWKS_KEYS = {}
    _ = AuthService.get_jwks_client()


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
# AuthService — token validation and user profile resolution
# ---------------------------------------------------------------------------


class AuthService:
    """Token validation and user profile resolution for agent-service."""

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_keycloak_enabled() -> bool:
        return settings.KEYCLOAK_ENABLED and bool(settings.KEYCLOAK_ISSUER_URL)

    @staticmethod
    def get_keycloak_issuer() -> str:
        issuer = (settings.KEYCLOAK_ISSUER_URL or "").strip()
        if not issuer:
            raise DependencyUnavailableError(
                message=t("auth.keycloak_not_configured"),
                details={"dependency": "keycloak"},
            )
        return issuer.rstrip("/")

    @staticmethod
    def get_keycloak_base_url() -> str:
        base_url = (settings.KEYCLOAK_BASE_URL or "").rstrip("/")
        if not base_url:
            issuer = AuthService.get_keycloak_issuer()
            if "/realms/" in issuer:
                base_url = issuer.split("/realms/")[0].rstrip("/")
        return base_url

    @staticmethod
    def get_keycloak_realm() -> str:
        realm = settings.KEYCLOAK_REALM
        if realm:
            return realm
        issuer = AuthService.get_keycloak_issuer()
        if "/realms/" in issuer:
            return issuer.split("/realms/")[-1].split("/")[0]
        return "agenticai"

    @staticmethod
    def get_jwks_client() -> PyJWKClient:
        global _JWKS_CLIENT
        if _JWKS_CLIENT is None:
            jwks_url = f"{AuthService.get_keycloak_issuer()}/protocol/openid-connect/certs"
            _JWKS_CLIENT = PyJWKClient(jwks_url, cache_keys=True)
        return _JWKS_CLIENT

    @staticmethod
    def get_signing_key(token: str) -> Any:
        """Get signing key for a JWT, with key rotation support."""
        client = AuthService.get_jwks_client()
        try:
            return client.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as exc:
            _refresh_jwks()
            try:
                return AuthService.get_jwks_client().get_signing_key_from_jwt(token)
            except jwt.PyJWKClientError as refreshed_exc:
                logger.warning(
                    "Keycloak signing key not found after JWKS refresh: %s", refreshed_exc
                )
                raise exc from refreshed_exc

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    @staticmethod
    def decode_keycloak_token(token: str) -> dict[str, Any]:
        issuer = AuthService.get_keycloak_issuer()
        audience_env = (settings.KEYCLOAK_AUDIENCE or "").strip()
        client_id = settings.KEYCLOAK_CLIENT_ID or ""
        leeway = settings.KEYCLOAK_TOKEN_LEEWAY_SECONDS

        audiences = [a.strip() for a in audience_env.split(",") if a.strip()]
        if client_id and client_id not in audiences:
            audiences.append(client_id)

        try:
            signing_key = AuthService.get_signing_key(token)
            claims = jwt.decode(
                jwt=token,
                key=signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                issuer=issuer,
                audience=audiences if audiences else None,
                leeway=leeway,
                options={
                    "verify_aud": bool(audiences),
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_iat": False,
                },
            )
            return claims
        except jwt.PyJWKClientError as exc:
            logger.warning("Failed to resolve Keycloak signing key: %s", exc)
            raise UnauthorizedError(
                message=t("auth.signing_key_resolution_failed", error=str(exc)),
            ) from exc
        except InvalidTokenError as exc:
            raise UnauthorizedError(
                message=t("auth.invalid_bearer_token_detail", error=str(exc)),
            ) from exc
        except Exception as exc:
            logger.exception("Failed to validate Keycloak token")
            raise UnauthorizedError(
                message=t("auth.token_validation_failed"),
            ) from exc

    @staticmethod
    def extract_user_id_from_token(token: str) -> str | None:
        if not token:
            return None

        if AuthService.is_keycloak_enabled():
            claims = AuthService.decode_keycloak_token(token)
            return claims.get("sub") or claims.get("preferred_username") or claims.get("email")

        if token.startswith("api-key:"):
            return token[8:]

        return token

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
        user_id = str(
            claims.get("sub")
            or claims.get("preferred_username")
            or claims.get("email")
            or "unknown"
        )
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

        if token and self.is_keycloak_enabled():
            try:
                claims = self.decode_keycloak_token(token)
                keycloak_id = keycloak_id or claims.get("sub")
            except ApplicationError:
                pass

        if not keycloak_id:
            keycloak_id = user_id

        if not user_service_user and keycloak_id:
            try:
                from service.UserServiceClient import get_user_by_keycloak_id

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

    async def get_current_user(self, token: str | None, user: AuthenticatedUser) -> dict[str, Any]:
        identity = await self.resolve_user_identity(token=token, user_id=user.user_id, user=user)
        keycloak_id = identity.get("keycloak_id")
        user_service_user = identity.get("user_service_user")
        effective_user_id = str(identity.get("primary_user_id") or user.user_id)

        keycloak_profile = await get_keycloak_user_profile(keycloak_id or user.user_id)

        email = (
            user.email or (user_service_user and user_service_user.get("email")) or user.username
        )
        username = user.username or (user_service_user and user_service_user.get("username"))
        if not email and isinstance(keycloak_profile, dict):
            email = keycloak_profile.get("email") or keycloak_profile.get("username")
        if not username and isinstance(keycloak_profile, dict):
            username = keycloak_profile.get("username")
        if not username and isinstance(email, str) and "@" in email:
            username = email.split("@", 1)[0]
        if not email:
            email = user.user_id if "@" in user.user_id else "user@local.dev"

        given_name = user.claims.get("given_name") or user.claims.get("first_name")
        family_name = user.claims.get("family_name") or user.claims.get("last_name")
        if user_service_user:
            given_name = user_service_user.get("first_name") or given_name
            family_name = user_service_user.get("last_name") or family_name

        kc_first = None
        kc_last = None
        if isinstance(keycloak_profile, dict):
            kc_first = keycloak_profile.get("firstName")
            kc_last = keycloak_profile.get("lastName")

        full_name = user.claims.get("name")
        if user_service_user and (
            user_service_user.get("first_name") or user_service_user.get("last_name")
        ):
            first = user_service_user.get("first_name") or ""
            last = user_service_user.get("last_name") or ""
            full_name = f"{first} {last}".strip()
        if kc_first:
            full_name = f"{kc_first} {kc_last}".strip() if kc_last else str(kc_first)
        elif not full_name and given_name:
            full_name = f"{given_name} {family_name}".strip() if family_name else str(given_name)

        role = "enduser"
        if isinstance(user_service_user, dict) and user_service_user.get("role"):
            role = str(user_service_user["role"])

        user_settings_dict: dict[str, Any] = {}
        try:
            user_settings_dict = await get_user_settings(effective_user_id)
        except Exception:
            logger.warning(
                "Failed to load user settings for user %s, using defaults", effective_user_id
            )

        personalization_name = full_name or given_name or str(email).split("@")[0]
        personalization_role = str(user_settings_dict.get("work_role") or "")

        return {
            "id": effective_user_id,
            "email": str(email),
            "username": str(username) if username else None,
            "is_active": True,
            "is_verified": True,
            "role": role,
            "preferences": {
                "chosen_assistants": None,
                "visible_assistants": [],
                "hidden_assistants": [],
                "default_model": user_settings_dict.get("default_model"),
                "recent_assistants": [],
                "auto_scroll": user_settings_dict.get("auto_scroll", True),
                "shortcut_enabled": user_settings_dict.get("shortcut_enabled", True),
                "temperature_override_enabled": False,
                "theme_preference": user_settings_dict.get("theme_preference"),
                "chat_background": user_settings_dict.get("chat_background"),
                "default_app_mode": user_settings_dict.get("default_app_mode", "AUTO"),
            },
            "team_name": None,
            "is_anonymous_user": False,
            "password_configured": True,
            "is_external_keycloak_user": bool(
                user_service_user.get("is_external_keycloak_user", False)
            )
            if isinstance(user_service_user, dict)
            else False,
            "first_name": str(given_name) if given_name else None,
            "last_name": str(family_name) if family_name else None,
            "full_name": str(full_name) if full_name else None,
            "personalization": {
                "name": str(personalization_name),
                "role": str(personalization_role),
                "memories": [],
                "use_memories": False,
                "enable_memory_tool": False,
                "user_preferences": user_settings_dict.get("user_preferences", ""),
                "long_term_memory_enabled": user_settings_dict.get(
                    "long_term_memory_enabled", False
                ),
                "extract_memory": user_settings_dict.get("extract_memory", True),
            },
        }


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
        identity = await get_auth_service().resolve_user_identity(
            token=token, user_id=raw, user=user
        )
        known = [str(candidate) for candidate in identity.get("known_user_ids") or [] if candidate]
    except Exception as exc:  # noqa: BLE001 - never let identity resolution break a lookup
        logger.warning("Failed to resolve known user ids for %s: %s", raw, exc)
        known = []
    if raw not in known:
        known.append(raw)
    return known
