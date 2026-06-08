"""
Authentication service.

Single source of truth for all authentication business logic:
login, logout, OIDC token exchange, Keycloak session management,
token validation, and API key verification.
"""

import logging as _stdlib_logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient

from core.logger import get_logger
from service.UserServiceClient import get_user_settings

__all__ = [
    "AuthService",
    "get_auth_service",
    "get_primary_user_id",
    "verify_bearer",
    "extract_user_id_from_token",
    "verify_api_key",
]

logger = get_logger(__name__)
logger_stdlib = _stdlib_logging.getLogger(__name__)

# Valid API keys (comma-separated in environment variable)
VALID_API_KEYS: set = set()
_JWKS_CLIENT: PyJWKClient | None = None
_auth_service: "AuthService | None" = None


def _get_valid_api_keys() -> set:
    """Get valid API keys from environment variable."""
    global VALID_API_KEYS
    if not VALID_API_KEYS:
        api_keys_env = os.environ.get("VALID_API_KEYS", "")
        if api_keys_env:
            VALID_API_KEYS = set(k.strip() for k in api_keys_env.split(",") if k.strip())
    return VALID_API_KEYS


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


class AuthService:
    """Service layer for authentication business logic.

    Owns all Keycloak interaction, OIDC flows, token exchange,
    session termination, and user profile resolution.
    """

    def __init__(self, user_id: str = "dev-user-1"):
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_keycloak_enabled() -> bool:
        enabled = os.environ.get("KEYCLOAK_ENABLED", "false").lower() == "true"
        return enabled and bool(os.environ.get("KEYCLOAK_ISSUER_URL"))

    @staticmethod
    def get_keycloak_issuer() -> str:
        issuer = os.environ.get("KEYCLOAK_ISSUER_URL", "").strip()
        if not issuer:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="KEYCLOAK_ISSUER_URL is not configured",
            )
        return issuer.rstrip("/")

    @staticmethod
    def get_keycloak_base_url() -> str:
        base_url = (os.environ.get("KEYCLOAK_BASE_URL") or "").rstrip("/")
        if not base_url:
            issuer = AuthService.get_keycloak_issuer()
            if "/realms/" in issuer:
                base_url = issuer.split("/realms/")[0].rstrip("/")
        return base_url

    @staticmethod
    def get_keycloak_realm() -> str:
        realm = os.environ.get("KEYCLOAK_REALM")
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
            _JWKS_CLIENT = PyJWKClient(jwks_url)
        return _JWKS_CLIENT

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    @staticmethod
    def decode_keycloak_token(token: str) -> dict[str, Any]:
        issuer = AuthService.get_keycloak_issuer()
        audience_env = os.environ.get("KEYCLOAK_AUDIENCE", "").strip()
        client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "").strip()
        leeway = int(os.environ.get("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120"))
        audiences = [a.strip() for a in audience_env.split(",") if a.strip()]
        if client_id and client_id not in audiences:
            audiences.append(client_id)

        try:
            signing_key = AuthService.get_jwks_client().get_signing_key_from_jwt(token)
            base_decode_kwargs = {
                "jwt": token,
                "key": signing_key.key,
                "algorithms": ["RS256", "RS384", "RS512"],
                "issuer": issuer,
                "leeway": leeway,
            }

            claims = jwt.decode(**base_decode_kwargs, options={"verify_aud": False})

            if not audiences:
                return claims

            token_aud = claims.get("aud")
            aud_list: list[str] = []
            if isinstance(token_aud, str):
                aud_list = [token_aud]
            elif isinstance(token_aud, list):
                aud_list = [str(a) for a in token_aud]

            azp = str(claims.get("azp", ""))
            if any(a in aud_list for a in audiences) or (azp and azp in audiences):
                return claims

            raise InvalidTokenError(
                f"No matching audience found. expected one of {audiences}, got aud={aud_list}, azp={azp}"
            )
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
    def decode_jwt_without_verification(token: str | None) -> dict[str, Any]:
        if not token:
            return {}
        try:
            decoded = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                },
                algorithms=["RS256", "HS256", "RS384", "RS512"],
            )
            if isinstance(decoded, dict):
                return decoded
            return {}
        except Exception:
            return {}

    async def resolve_user_identity(
        self,
        request: Request,
        user_id: str | None,
    ) -> dict[str, Any]:
        claims = self.decode_jwt_without_verification(_extract_auth_token(None, request))
        keycloak_id = claims.get("sub") or user_id

        user_service_user = None
        if keycloak_id:
            try:
                from service.UserServiceClient import get_user_by_keycloak_id

                user_service_user = await get_user_by_keycloak_id(str(keycloak_id))
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

    # ------------------------------------------------------------------
    # Keycloak admin API
    # ------------------------------------------------------------------

    async def get_keycloak_admin_token(self) -> str | None:
        base_url = self.get_keycloak_base_url()
        if not base_url:
            return None

        admin_realm = os.environ.get("KEYCLOAK_ADMIN_REALM", "master")
        admin_user = os.environ.get("KEYCLOAK_ADMIN") or os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin")
        admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin123")

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

    # ------------------------------------------------------------------
    # Auth type metadata
    # ------------------------------------------------------------------

    async def get_auth_type(self) -> dict[str, Any]:
        keycloak_enabled = self.is_keycloak_enabled()
        return {
            "authType": "oidc" if keycloak_enabled else "basic",
            "autoRedirect": False,
            "requiresVerification": False,
            "anonymousUserEnabled": False,
            "passwordMinLength": 8,
            "hasUsers": True,
            "oauthEnabled": keycloak_enabled,
        }

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def basic_login(self, username: str, password: str) -> dict[str, Any]:
        if self.is_keycloak_enabled():
            return {
                "success": False,
                "error": "Password login is disabled when OIDC is enabled.",
            }

        if username and password:
            return {
                "success": True,
                "user_id": self._user_id,
                "email": f"{username}@example.com",
            }

        return {"success": False, "error": "Missing credentials"}

    # ------------------------------------------------------------------
    # Logout — terminates Keycloak SSO session server-side
    # ------------------------------------------------------------------

    async def logout(self, refresh_token: str | None = None, id_token_hint: str | None = None) -> dict[str, Any]:
        if self.is_keycloak_enabled():
            await self._keycloak_backchannel_logout(refresh_token=refresh_token, id_token_hint=id_token_hint)
        return {"success": True}

    async def _keycloak_backchannel_logout(
        self,
        refresh_token: str | None = None,
        id_token_hint: str | None = None,
    ) -> None:
        issuer = self.get_keycloak_issuer()
        client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "agenticai-web")
        client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET")

        if refresh_token:
            logout_url = f"{issuer}/protocol/openid-connect/logout"
            payload: dict[str, str] = {
                "client_id": client_id,
                "refresh_token": refresh_token,
            }
            if client_secret:
                payload["client_secret"] = client_secret
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(logout_url, data=payload)
            except Exception:
                logger.warning("Keycloak backchannel logout with refresh_token failed, trying id_token_hint")
                refresh_token = None

        if not refresh_token and id_token_hint:
            logout_url = f"{issuer}/protocol/openid-connect/logout?id_token_hint={id_token_hint}"
            logout_url += f"&client_id={client_id}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.get(logout_url)
            except Exception as e:
                logger.warning(f"Keycloak backchannel logout with id_token_hint failed: {e}")

    # ------------------------------------------------------------------
    # OIDC authorize URL
    # ------------------------------------------------------------------

    async def get_oidc_authorize_url(
        self,
        next_url: str | None = None,
        redirect_uri_override: str | None = None,
    ) -> dict[str, str]:
        keycloak_enabled = self.is_keycloak_enabled()
        issuer = self.get_keycloak_issuer()

        if not keycloak_enabled or not issuer:
            raise ValueError("OIDC is not configured. Set KEYCLOAK_ENABLED and KEYCLOAK_ISSUER_URL.")

        client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "agenticai-web")
        redirect_uri = (
            redirect_uri_override
            or os.environ.get(
                "KEYCLOAK_REDIRECT_URI",
                "http://localhost:3000/auth/oidc/callback",
            )
        )
        scope = os.environ.get("KEYCLOAK_SCOPE", "openid profile email")

        params: dict[str, str] = {
            "client_id": client_id,
            "response_type": "code",
            "scope": scope,
            "redirect_uri": redirect_uri,
        }
        if next_url:
            params["state"] = next_url

        auth_url = f"{issuer}/protocol/openid-connect/auth?{urlencode(params)}"
        return {"authorization_url": auth_url}

    # ------------------------------------------------------------------
    # OIDC callback — exchange code for tokens
    # ------------------------------------------------------------------

    async def handle_oidc_callback(
        self,
        code: str,
        state: str | None,
        redirect_uri_override: str | None = None,
    ) -> dict[str, Any]:
        from service.UserServiceClient import upsert_user_from_keycloak

        keycloak_enabled = self.is_keycloak_enabled()
        issuer = self.get_keycloak_issuer()
        client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "agenticai-web")
        client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET")
        redirect_uri = (
            redirect_uri_override
            or os.environ.get(
                "KEYCLOAK_REDIRECT_URI",
                "http://localhost:3000/auth/oidc/callback",
            )
        )

        if not keycloak_enabled or not issuer:
            raise ValueError("OIDC is not configured. Set KEYCLOAK_ENABLED and KEYCLOAK_ISSUER_URL.")

        token_url = f"{issuer}/protocol/openid-connect/token"
        payload: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if client_secret:
            payload["client_secret"] = client_secret

        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(token_url, data=payload)
            token_response.raise_for_status()
            token_data = token_response.json()

        access_token = token_data.get("access_token")
        id_token = token_data.get("id_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in", 3600))

        if not access_token:
            raise ValueError("Keycloak token response did not include access_token")

        decoded_id_token = self.decode_jwt_without_verification(id_token or "")
        keycloak_id = decoded_id_token.get("sub")
        email = decoded_id_token.get("email") or decoded_id_token.get("preferred_username") or ""
        first_name = decoded_id_token.get("given_name")
        last_name = decoded_id_token.get("family_name")
        username = decoded_id_token.get("preferred_username")

        if keycloak_id:
            try:
                await upsert_user_from_keycloak(
                    keycloak_id=keycloak_id,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                )
            except Exception as exc:
                logger.warning(f"Failed to sync user to user-service: {exc}")

        redirect_url = state or "/"
        return {
            "success": True,
            "redirect_url": redirect_url,
            "oidc_expiry": datetime.now(UTC).isoformat(),
            "id_token": id_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
        }

    # ------------------------------------------------------------------
    # Current user profile
    # ------------------------------------------------------------------

    @staticmethod
    def _read_attr(attributes: Any, key: str) -> str | None:
        if not isinstance(attributes, dict):
            return None
        value = attributes.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
        return None

    async def get_current_user(self, request: Request, user_id: str) -> dict[str, Any]:
        claims: dict[str, Any] = {}
        for cookie_name in ("id_token", "fastapiusersauth", "session"):
            claims.update(self.decode_jwt_without_verification(request.cookies.get(cookie_name)))

        identity = await self.resolve_user_identity(request=request, user_id=user_id)
        keycloak_id = identity.get("keycloak_id")
        user_service_user = identity.get("user_service_user")
        effective_user_id = str(identity.get("primary_user_id") or user_id)

        # If user found in user-service, use those values with preference for Keycloak claims

        keycloak_profile = await self.get_keycloak_user_profile(keycloak_id or user_id)
        profile_attrs = (keycloak_profile or {}).get("attributes") if isinstance(keycloak_profile, dict) else None

        # Prioritize user-service data, fallback to claims and profile
        email = (
            claims.get("email") 
            or (user_service_user and user_service_user.get("email"))
            or claims.get("preferred_username")
        )
        username = (
            claims.get("preferred_username")
            or (user_service_user and user_service_user.get("username"))
        )
        if not email and isinstance(keycloak_profile, dict):
            email = keycloak_profile.get("email") or keycloak_profile.get("username")
        if not username and isinstance(keycloak_profile, dict):
            username = keycloak_profile.get("username")
        if not username and isinstance(email, str) and "@" in email:
            username = email.split("@", 1)[0]
        if not email:
            email = user_id if "@" in user_id else "user@local.dev"

        given_name = claims.get("given_name") or claims.get("first_name")
        family_name = claims.get("family_name") or claims.get("last_name")
        # Prefer user-service names
        if user_service_user:
            given_name = user_service_user.get("first_name") or given_name
            family_name = user_service_user.get("last_name") or family_name


        kc_first = None
        kc_last = None
        if isinstance(keycloak_profile, dict):
            kc_first = keycloak_profile.get("firstName")
            kc_last = keycloak_profile.get("lastName")

        full_name = claims.get("name")
        if user_service_user and (user_service_user.get("first_name") or user_service_user.get("last_name")):
            first = user_service_user.get("first_name") or ""
            last = user_service_user.get("last_name") or ""
            full_name = f"{first} {last}".strip()
        if kc_first:
            full_name = f"{kc_first} {kc_last}".strip() if kc_last else str(kc_first)
        elif not full_name and given_name:
            full_name = f"{given_name} {family_name}".strip() if family_name else str(given_name)

        role = "basic"
        claim_roles: set[str] = set()

        direct_role = claims.get("role")
        if isinstance(direct_role, str):
            claim_roles.add(direct_role.lower())
        direct_roles = claims.get("roles")
        if isinstance(direct_roles, list):
            claim_roles.update(str(r).lower() for r in direct_roles)

        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            roles = realm_access.get("roles") or []
            if isinstance(roles, list):
                claim_roles.update(str(r).lower() for r in roles)

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            for client_data in resource_access.values():
                if isinstance(client_data, dict):
                    roles = client_data.get("roles") or []
                    if isinstance(roles, list):
                        claim_roles.update(str(r).lower() for r in roles)

        attr_role = self._read_attr(profile_attrs, "agentic_role")
        if attr_role:
            claim_roles.add(attr_role.lower())

        if any(r in {"admin", "super_admin", "superuser"} for r in claim_roles):
            role = "admin"
        elif any(r in {"global_curator"} for r in claim_roles):
            role = "global_curator"
        elif any(r in {"curator"} for r in claim_roles):
            role = "curator"
        elif any(r in {"limited"} for r in claim_roles):
            role = "limited"

        admin_username = (os.environ.get("KEYCLOAK_ADMIN") or os.environ.get("KEYCLOAK_ADMIN_USERNAME") or "").strip().lower()
        admin_email = (os.environ.get("KEYCLOAK_ADMIN_EMAIL") or "").strip().lower()
        email_lower = str(email).lower()
        preferred_username = str(claims.get("preferred_username") or "").lower()
        if role == "basic" and (
            (admin_email and email_lower == admin_email)
            or (admin_username and preferred_username == admin_username)
            or (admin_username and email_lower.startswith(f"{admin_username}@"))
        ):
            role = "admin"

        personalization_role = (
            self._read_attr(profile_attrs, "work_role")
            or self._read_attr(profile_attrs, "workRole")
            or str(claims.get("work_role") or claims.get("workRole") or "")
            or role
        )
        personalization_name = full_name or given_name or str(email).split("@")[0]

        user_settings: dict[str, Any] = {}
        try:
            user_settings = await get_user_settings(effective_user_id)
        except Exception:
            logger.warning("Failed to load user settings for user %s, using defaults", effective_user_id)

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
                "default_model": user_settings.get("default_model"),
                "recent_assistants": [],
                "auto_scroll": user_settings.get("auto_scroll", True),
                "shortcut_enabled": user_settings.get("shortcut_enabled", True),
                "temperature_override_enabled": False,
                "theme_preference": user_settings.get("theme_preference"),
                "chat_background": user_settings.get("chat_background"),
                "default_app_mode": user_settings.get("default_app_mode", "AUTO"),
            },
            "team_name": None,
            "is_anonymous_user": False,
            "password_configured": True,
            "first_name": str(given_name) if given_name else None,
            "full_name": str(full_name) if full_name else None,
            "personalization": {
                "name": str(personalization_name),
                "role": str(personalization_role),
                "memories": [],
                "use_memories": False,
                "enable_memory_tool": False,
                "user_preferences": user_settings.get("user_preferences", ""),
                "long_term_memory_enabled": user_settings.get("long_term_memory_enabled", False),
                "extract_memory": user_settings.get("extract_memory", True),
            },
        }


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


# ------------------------------------------------------------------
# Module-level FastAPI dependency functions
# (maintain backward compatibility)
# ------------------------------------------------------------------

def _is_keycloak_enabled() -> bool:
    return AuthService.is_keycloak_enabled()


def _get_keycloak_issuer() -> str:
    return AuthService.get_keycloak_issuer()


def _get_keycloak_jwks_client() -> PyJWKClient:
    return AuthService.get_jwks_client()


def _decode_keycloak_token(token: str) -> dict:
    return AuthService.decode_keycloak_token(token)


def extract_user_id_from_token(token: str) -> str | None:
    return AuthService.extract_user_id_from_token(token)


def get_primary_user_id(identity: dict[str, Any] | None, fallback_user_id: str | None) -> str | None:
    if identity and identity.get("primary_user_id"):
        return str(identity["primary_user_id"])
    if fallback_user_id:
        return str(fallback_user_id)
    return None


def verify_api_key(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            HTTPBearer(
                description="Please provide API key",
                auto_error=False,
            )
        ),
    ],
) -> str | None:
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

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    token = _extract_auth_token(http_auth, request)

    valid_keys = _get_valid_api_keys()
    if not valid_keys:
        return "dev-user"

    if not token:
        return None

    if token in valid_keys:
        return extract_user_id_from_token(token)

    user_id = extract_user_id_from_token(token)
    if user_id in valid_keys:
        return user_id

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def verify_bearer(
    request: Request,
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(
            HTTPBearer(
                description="Please provide API key",
                auto_error=False,
            )
        ),
    ],
) -> None:
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
        user_id = extract_user_id_from_token(token)
        if user_id in valid_keys:
            return
