import secrets
from typing import Any

from fastapi import Request
from jose import jwt

from src.core.database.models.user_model import normalize_user_role
from src.repository import UserRepository, UserSettingsRepository
from src.service.keycloak_service import get_keycloak_service


class ExternalAuthService:
    """OIDC authentication service for external Keycloak mode.

    Keycloak remains the identity provider. user-service mirrors the identity
    into the local DB so application-owned data can be keyed by local user id.
    """

    def __init__(self):
        self.keycloak = get_keycloak_service()
        self.user_repo = UserRepository()
        self.settings_repo = UserSettingsRepository()

    async def basic_login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate via Keycloak Direct Access Grant.

        Returns Keycloak tokens and ensures a local application user exists.
        """
        username = username.strip()
        token_data = await self.keycloak.password_grant(username, password)
        user = await self._upsert_local_user_from_token_data(token_data, fallback_username=username)
        return self._build_token_response(token_data, user)

    async def logout(self, refresh_token: str | None = None) -> dict[str, Any]:
        """Backchannel logout from Keycloak."""
        if refresh_token:
            await self.keycloak.backchannel_logout(refresh_token=refresh_token)
        return {"message": "Logged out successfully"}

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh tokens via Keycloak refresh token grant."""
        token_data = await self.keycloak.refresh_token_grant(refresh_token)
        user = await self._upsert_local_user_from_token_data(token_data)
        return self._build_token_response(token_data, user)

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate token via JWKS or userinfo fallback.

        Ensures a local user exists and returns local user identity on success.
        """
        claims = await self.keycloak.validate_token_jwks(token)
        if not claims:
            claims = await self.keycloak.get_user_info(token)

        if not claims:
            return None

        user = await self._upsert_local_user_from_claims(claims)
        return {
            "sub": str(user.id),
            "keycloak_sub": user.keycloak_id,
            "email": user.email,
            "role": normalize_user_role(user.role),
            "type": "access",
        }

    async def get_oidc_authorize_url(self, redirect_uri: str | None = None) -> str:
        uri = redirect_uri or "http://localhost:3000/auth/oidc/callback"
        state = secrets.token_urlsafe(16)
        return await self.keycloak.get_oidc_authorize_url(uri, state=state)

    async def handle_oidc_callback(
        self,
        code: str,
        redirect_uri: str,
        fallback_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        token_data = await self.keycloak.handle_oidc_callback(
            code,
            redirect_uri,
            fallback_redirect_uri=fallback_redirect_uri,
        )
        user = await self._upsert_local_user_from_token_data(token_data)
        return self._build_token_response(token_data, user)

    def get_auth_type(self) -> dict[str, Any]:
        return {
            "autoRedirect": False,
            "requiresVerification": False,
            "anonymousUserEnabled": True,
            "hasUsers": True,
            "authType": "oidc",
            "keycloakEnabled": True,
            "oauthEnabled": True,
            "externalKeycloak": True,
            "external_keycloak": True,
        }

    async def get_current_user(self, request: Request) -> dict[str, Any]:
        """Return local application user info for the validated access token.

        Extracts the token from the request, validates via JWKS/userinfo,
        upserts the local user, and returns the DB-backed profile.
        """
        token = self._extract_token(request)
        if not token:
            raise ValueError("No authentication token found")

        claims = await self.keycloak.validate_token_jwks(token)
        if not claims:
            claims = await self.keycloak.get_user_info(token)

        if not claims:
            raise ValueError("Invalid or expired token")

        user = await self._upsert_local_user_from_claims(claims)
        settings = await self.settings_repo.ensure_defaults(user.id)
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None
        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or None,
            "role": normalize_user_role(user.role),
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_superuser": user.is_superuser,
            "keycloak_id": user.keycloak_id,
            "preferences": {
                "chosen_assistants": None,
                "visible_assistants": [],
                "hidden_assistants": [],
                "default_model": settings.default_model,
                "default_provider_id": settings.default_provider_id,
                "recent_assistants": [],
                "auto_scroll": settings.auto_scroll,
                "shortcut_enabled": settings.shortcut_enabled,
                "temperature_override_enabled": False,
                "theme_preference": settings.theme_preference,
                "chat_background": settings.chat_background,
                "default_app_mode": settings.default_app_mode,
            },
            "personalization": {
                "name": full_name or user.username or user.email.split("@", 1)[0],
                "role": settings.work_role or "",
                "memories": settings.memories or [],
                "use_memories": settings.use_memories,
                "enable_memory_tool": settings.enable_memory_tool,
                "user_preferences": settings.user_preferences or "",
                "long_term_memory_enabled": settings.long_term_memory_enabled,
                "extract_memory": settings.extract_memory,
            },
        }

    @staticmethod
    def _extract_token(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]
        return request.cookies.get("access_token")

    @staticmethod
    def _extract_role(claims: dict[str, Any]) -> str:
        roles: list[str] = []

        realm_access = claims.get("realm_access")
        if isinstance(realm_access, dict):
            realm_roles_list = realm_access.get("roles", [])
            if isinstance(realm_roles_list, list):
                roles.extend(str(r) for r in realm_roles_list if r is not None)

        resource_access = claims.get("resource_access")
        if isinstance(resource_access, dict):
            for client_mapping in resource_access.values():
                if not isinstance(client_mapping, dict):
                    continue
                client_roles = client_mapping.get("roles", [])
                if isinstance(client_roles, list):
                    roles.extend(str(r) for r in client_roles if r is not None)

        role_map = {
            "admin": "admin",
            "super_admin": "admin",
            "superuser": "admin",
            "realm-admin": "admin",
        }
        for role in roles:
            normalized = role.strip().lower()
            if normalized in role_map:
                return role_map[normalized]
        return "enduser"

    async def _upsert_local_user_from_token_data(
        self,
        token_data: dict[str, Any],
        fallback_username: str | None = None,
    ):
        claims = self._claims_from_token_data(token_data)
        if not claims:
            raise ValueError("Authentication failed — no user claims received")
        if fallback_username and not claims.get("preferred_username"):
            claims["preferred_username"] = fallback_username
        return await self._upsert_local_user_from_claims(claims)

    async def _upsert_local_user_from_claims(self, claims: dict[str, Any]):
        keycloak_id = str(claims.get("sub") or "").strip()
        if not keycloak_id:
            raise ValueError("Authentication failed — no subject in token")

        username = str(claims.get("preferred_username") or "").strip() or None
        email = str(claims.get("email") or "").strip().lower()
        if not email:
            email = f"{username or keycloak_id}@external-keycloak.local"

        first_name = str(claims.get("given_name") or "").strip() or None
        last_name = str(claims.get("family_name") or "").strip() or None
        role = self._extract_role(claims)

        user = await self.user_repo.upsert_by_keycloak_id(
            keycloak_id,
            email=email,
            username=username or email.split("@", 1)[0],
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=True,
            is_verified=bool(claims.get("email_verified", True)),
        )
        await self.settings_repo.ensure_defaults(user.id)
        return user

    @staticmethod
    def _claims_from_token_data(token_data: dict[str, Any]) -> dict[str, Any] | None:
        for token_name in ("id_token", "access_token"):
            token = token_data.get(token_name)
            if not token:
                continue
            try:
                claims = jwt.get_unverified_claims(token)
            except Exception:
                continue
            if isinstance(claims, dict) and claims.get("sub"):
                return claims
        return None

    @staticmethod
    def _build_token_response(token_data: dict[str, Any], user) -> dict[str, Any]:
        payload = {
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "id_token": token_data.get("id_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": int(token_data.get("expires_in", 3600)),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": normalize_user_role(user.role),
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "is_superuser": user.is_superuser,
                "keycloak_id": user.keycloak_id,
            },
        }
        return payload


_external_auth_service: ExternalAuthService | None = None


def get_external_auth_service() -> ExternalAuthService:
    global _external_auth_service
    if _external_auth_service is None:
        _external_auth_service = ExternalAuthService()
    return _external_auth_service
