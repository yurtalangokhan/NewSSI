"""
Authentication helpers.

Agent-service does not issue, refresh, or revoke user tokens. User-service owns
login, logout, registration, and OIDC flows. This module only validates incoming
tokens and resolves user context for protected agent-service endpoints.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient

from core.logger import get_logger
from core.settings import settings
from service.UserServiceClient import (
    get_current_user as get_user_service_current_user,
)
from service.UserServiceClient import (
    get_user_settings,
    set_current_access_token,
)

__all__ = [
    "AuthService",
    "get_auth_service",
    "AuthenticatedUser",
    "require_user",
    "require_permission",
    "require_user_or_internal_service_token",
    "get_primary_user_id",
    "verify_bearer",
    "verify_bearer_or_internal_service_token",
    "extract_user_id_from_token",
    "verify_api_key",
]

logger = get_logger(__name__)

_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_KEYS: dict[str, Any] = {}  # kid -> key cache
_auth_service: "AuthService | None" = None


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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="KEYCLOAK_ISSUER_URL is not configured",
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
                logger.warning("Keycloak signing key not found after JWKS refresh: %s", refreshed_exc)
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
                },
            )
            return claims
        except jwt.PyJWKClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unable to resolve token signing key: {exc}",
            ) from exc
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid bearer token: {exc}",
            ) from exc
        except Exception as exc:
            logger.exception("Failed to validate Keycloak token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed",
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
        if user_data.get("is_superuser") and "admin" not in roles:
            roles.append("admin")

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
        except HTTPException as exc:
            if exc.status_code in {
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            }:
                return None
            raise
        if not user_data:
            return None
        return AuthService.build_authenticated_user_from_user_service(user_data, token)

    async def resolve_user_identity(
        self,
        request: Request,
        user_id: str | None,
        user: AuthenticatedUser | None = None,
    ) -> dict[str, Any]:
        token = _extract_auth_token(None, request)
        user_service_user = None
        keycloak_id = user.claims.get("keycloak_id") if user else None
        if user and isinstance(user.claims.get("user_service_user"), dict):
            user_service_user = user.claims["user_service_user"]

        if token and self.is_keycloak_enabled():
            try:
                claims = self.decode_keycloak_token(token)
                keycloak_id = keycloak_id or claims.get("sub")
            except HTTPException:
                pass

        if not keycloak_id:
            keycloak_id = user_id

        if not user_service_user and keycloak_id and str(keycloak_id) != str(user_id):
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

    async def get_current_user(self, request: Request, user: AuthenticatedUser) -> dict[str, Any]:
        identity = await self.resolve_user_identity(request=request, user_id=user.user_id, user=user)
        keycloak_id = identity.get("keycloak_id")
        user_service_user = identity.get("user_service_user")
        effective_user_id = str(identity.get("primary_user_id") or user.user_id)

        keycloak_profile = await self.get_keycloak_user_profile(keycloak_id or user.user_id)

        email = (
            user.email
            or (user_service_user and user_service_user.get("email"))
            or user.username
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
            full_name = (
                f"{given_name} {family_name}".strip() if family_name else str(given_name)
            )

        role = "basic"
        if any(r in {"admin", "super_admin", "superuser"} for r in user.roles):
            role = "admin"
        elif any(r in {"global_curator"} for r in user.roles):
            role = "global_curator"
        elif any(r in {"curator"} for r in user.roles):
            role = "curator"
        elif any(r in {"limited"} for r in user.roles):
            role = "limited"

        admin_email = (settings.KEYCLOAK_ADMIN_EMAIL or "").strip().lower()
        email_lower = str(email).lower()
        if role == "basic" and admin_email and email_lower == admin_email:
            role = "admin"

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
            "is_superuser": role == "admin",
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

    # ------------------------------------------------------------------
    # Keycloak admin API
    # ------------------------------------------------------------------

    async def get_keycloak_admin_token(self) -> str | None:
        base_url = self.get_keycloak_base_url()
        if not base_url:
            return None

        admin_realm = "master"
        admin_user = "admin"
        admin_password = "admin123"

        token_url = f"{base_url}/realms/{admin_realm}/protocol/openid-connect/token"
        payload = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_password,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(token_url, data=payload)
            if not response.is_success:
                return None
            return response.json().get("access_token")
        except Exception:
            return None

    async def get_keycloak_user_profile(self, user_id: str) -> dict[str, Any] | None:
        issuer = self.get_keycloak_issuer()
        if "/realms/" not in issuer:
            return None

        base_url = issuer.split("/realms/")[0].rstrip("/")
        realm = issuer.split("/realms/")[-1].split("/")[0]
        admin_token = await self.get_keycloak_admin_token()
        if not admin_token:
            return None

        headers = {"Authorization": f"Bearer {admin_token}"}
        user_url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(user_url, headers=headers)
            if not response.is_success:
                return None
            data = response.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


# ------------------------------------------------------------------
# JWKS key rotation helper
# ------------------------------------------------------------------


def _refresh_jwks() -> None:
    global _JWKS_CLIENT, _JWKS_KEYS
    _JWKS_CLIENT = None
    _JWKS_KEYS = {}
    _ = AuthService.get_jwks_client()


# ------------------------------------------------------------------
# Module-level auth helpers
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Primary FastAPI dependencies (use these in routes)
# ------------------------------------------------------------------


async def require_user(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> AuthenticatedUser:
    """Validate bearer token and return authenticated user context.

    Raises HTTPException(401) if token is missing or invalid.
    """
    token = _extract_auth_token(http_auth, request)
    set_current_access_token(token)

    if _is_keycloak_enabled():
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
            )
        try:
            claims = _decode_keycloak_token(token)
            user = await AuthService.authenticate_with_user_service(token)
            if user:
                return user
            return AuthService.build_authenticated_user(claims, token)
        except HTTPException as exc:
            user = await AuthService.authenticate_with_user_service(token)
            if user:
                return user
            raise exc

    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        # No keys configured — dev mode, allow all
        return AuthenticatedUser(user_id="dev-user", email="dev@local.dev")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid bearer token",
    )


def require_permission(permission: str):
    """Factory returning a FastAPI dependency requiring a specific permission.

    Usage: ``user = Depends(require_permission("datasource:create"))``

    Authenticates via require_user, then fetches the user's resolved permissions
    from user-service and verifies membership. Dev mode and internal-service bypass.
    """

    async def _check_permission(
        user: AuthenticatedUser = Depends(require_user),
    ) -> AuthenticatedUser:
        if user.user_id in ("dev-user", "internal-service"):
            return user

        try:
            from service.UserServiceClient import get_user_permissions

            perm_data = await get_user_permissions(user.user_id, user.access_token)
            user_perms = perm_data.get("permissions", [])
            if user_perms == ["*"] or permission in user_perms:
                return user
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
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
    internal_token = settings.INTERNAL_SERVICE_TOKEN or ""
    token = _extract_auth_token(http_auth, request)

    if token and internal_token and token == internal_token:
        return AuthenticatedUser(
            user_id="internal-service",
            email="internal@service.local",
            roles=["internal"],
            access_token=token,
        )

    return await require_user(request=request, http_auth=http_auth)


# ------------------------------------------------------------------
# Backward-compatible aliases (deprecated — use require_user instead)
# ------------------------------------------------------------------


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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid bearer token",
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
            except HTTPException:
                continue
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
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
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


def verify_bearer_or_internal_service_token(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide a bearer token", auto_error=False)),
    ],
) -> None:
    """Deprecated: use require_user_or_internal_service_token instead."""
    token = _extract_auth_token(http_auth, request)
    internal_token = settings.INTERNAL_SERVICE_TOKEN or ""

    if token and internal_token and token == internal_token:
        return

    verify_bearer(request=request, http_auth=http_auth)
