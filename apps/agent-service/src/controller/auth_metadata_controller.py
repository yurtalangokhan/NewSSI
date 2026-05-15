"""Controller for auth metadata and session-oriented auth endpoints."""

import logging
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Request, Response

from controller.base import BaseController
from core.db.repositories.user_settings_repo import (
    DEFAULT_USER_SETTINGS,
    UserSettingsRepository,
)

logger = logging.getLogger(__name__)


class AuthMetadataController(BaseController):
    """Controller for auth metadata, user info, and auth session helpers."""

    def __init__(self, user_id: str = "dev-user-1"):
        self._user_id = user_id
        self._user_settings_repo = UserSettingsRepository()

    async def get_auth_type(self) -> dict[str, Any]:
        keycloak_enabled = os.getenv("KEYCLOAK_ENABLED", "false").lower() == "true"
        return {
            "authType": "oidc" if keycloak_enabled else "basic",
            "autoRedirect": False,
            "requiresVerification": False,
            "anonymousUserEnabled": False,
            "passwordMinLength": 8,
            "hasUsers": True,
            "oauthEnabled": keycloak_enabled,
        }

    def _decode_jwt_without_verification(self, token: str | None) -> dict[str, Any]:
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

    async def _get_keycloak_admin_token(self) -> str | None:
        base_url = (os.getenv("KEYCLOAK_BASE_URL") or "").rstrip("/")
        if not base_url:
            issuer = (os.getenv("KEYCLOAK_ISSUER_URL") or "").rstrip("/")
            if "/realms/" in issuer:
                base_url = issuer.split("/realms/")[0].rstrip("/")
        if not base_url:
            return None

        admin_realm = os.getenv("KEYCLOAK_ADMIN_REALM", "master")
        admin_user = os.getenv("KEYCLOAK_ADMIN") or os.getenv("KEYCLOAK_ADMIN_USERNAME", "admin")
        admin_password = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "admin123")

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

    async def _get_keycloak_user_profile(self, user_id: str) -> dict[str, Any] | None:
        issuer = (os.getenv("KEYCLOAK_ISSUER_URL") or "").rstrip("/")
        if "/realms/" not in issuer:
            return None

        base_url = issuer.split("/realms/")[0].rstrip("/")
        realm = issuer.split("/realms/")[-1].split("/")[0]
        admin_token = await self._get_keycloak_admin_token()
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
            claims.update(self._decode_jwt_without_verification(request.cookies.get(cookie_name)))

        keycloak_profile = await self._get_keycloak_user_profile(user_id)
        profile_attrs = (keycloak_profile or {}).get("attributes") if isinstance(keycloak_profile, dict) else None

        email = claims.get("email") or claims.get("preferred_username")
        if not email and isinstance(keycloak_profile, dict):
            email = keycloak_profile.get("email") or keycloak_profile.get("username")
        if not email:
            email = user_id if "@" in user_id else "user@local.dev"

        given_name = claims.get("given_name") or claims.get("first_name")
        family_name = claims.get("family_name") or claims.get("last_name")
        if isinstance(keycloak_profile, dict):
            given_name = given_name or keycloak_profile.get("firstName")
            family_name = family_name or keycloak_profile.get("lastName")
        full_name = claims.get("name")
        if not full_name and given_name:
            full_name = f"{given_name} {family_name}".strip() if family_name else str(given_name)
        if not full_name and isinstance(keycloak_profile, dict):
            kc_first = keycloak_profile.get("firstName")
            kc_last = keycloak_profile.get("lastName")
            if kc_first:
                full_name = f"{kc_first} {kc_last}".strip() if kc_last else str(kc_first)

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

        admin_username = (os.getenv("KEYCLOAK_ADMIN") or os.getenv("KEYCLOAK_ADMIN_USERNAME") or "").strip().lower()
        admin_email = (os.getenv("KEYCLOAK_ADMIN_EMAIL") or "").strip().lower()
        email_lower = str(email).lower()
        preferred_username = str(claims.get("preferred_username") or "").lower()
        if role == "basic" and (
            (admin_email and email_lower == admin_email)
            or (admin_username and preferred_username == admin_username)
            or (admin_username and email_lower.startswith(f"{admin_username}@"))
        ):
            role = "admin"

        personalization_role = self._read_attr(profile_attrs, "work_role") or ""
        personalization_name = full_name or given_name or str(email).split("@")[0]

        user_settings = dict(DEFAULT_USER_SETTINGS)
        try:
            user_settings = await self._user_settings_repo.ensure_defaults(user_id)
        except Exception as exc:
            logger.warning("Failed to load user_settings for %s: %s", user_id, exc)

        return {
            "id": user_id,
            "email": str(email),
            "is_active": True,
            "is_superuser": role == "admin",
            "is_verified": True,
            "role": role,
            "preferences": {
                "chosen_assistants": None,
                "visible_assistants": [],
                "hidden_assistants": [],
                "default_model": user_settings["default_model"],
                "recent_assistants": [],
                "auto_scroll": user_settings["auto_scroll"],
                "shortcut_enabled": user_settings["shortcut_enabled"],
                "temperature_override_enabled": False,
                "theme_preference": user_settings["theme_preference"],
                "chat_background": user_settings["chat_background"],
                "default_app_mode": user_settings["default_app_mode"],
            },
            "team_name": None,
            "is_anonymous_user": False,
            "password_configured": True,
            "first_name": str(given_name) if given_name else None,
            "full_name": str(full_name) if full_name else None,
            "personalization": {
                "name": str(personalization_name),
                "role": str(personalization_role),
                "extract_memory": user_settings["extract_memory"],
                "long_term_memory_enabled": user_settings["long_term_memory_enabled"],
                "user_preferences": user_settings["user_preferences"],
            },
        }

    async def login(self, username: str, password: str, response: Response) -> dict[str, Any]:
        if os.getenv("KEYCLOAK_ENABLED", "false").lower() == "true":
            response.status_code = 400
            return {
                "success": False,
                "error": "Password login is disabled when OIDC is enabled.",
            }

        if username and password:
            response.set_cookie("session", "dev-session", httponly=True, samesite="lax")
            return {
                "success": True,
                "user_id": self._user_id,
                "email": f"{username}@example.com",
            }

        response.status_code = 400
        return {"success": False, "error": "Missing credentials"}

    async def logout(self, response: Response) -> dict[str, Any]:
        # Delete all auth-related cookies for both basic and OIDC auth
        cookies_to_delete = ["session", "fastapiusersauth", "id_token", "refresh_token", "access_token"]
        for cookie_name in cookies_to_delete:
            response.delete_cookie(cookie_name, path="/", samesite="lax")
        
        return {"success": True}

    async def get_settings(self) -> dict[str, Any]:
        return {
            "auto_scroll": True,
            "application_status": "active",
            "gpu_enabled": False,
            "maximum_chat_retention_days": None,
            "notifications": [],
            "needs_reindexing": False,
            "anonymous_user_enabled": False,
            "invite_only_enabled": False,
            "deep_research_enabled": True,
            "temperature_override_enabled": True,
            "query_history_type": "normal",
        }

    async def get_enterprise_settings(self) -> dict[str, Any]:
        return {"application_name": "Agentic AI", "use_custom_logo": False}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def refresh_auth(self) -> dict[str, Any]:
        return {"success": True}

    async def get_oidc_authorize_url(
        self,
        next_url: str | None = None,
        redirect_uri_override: str | None = None,
    ) -> dict[str, str]:
        keycloak_enabled = os.getenv("KEYCLOAK_ENABLED", "false").lower() == "true"
        issuer = (os.getenv("KEYCLOAK_ISSUER_URL") or "").rstrip("/")

        if not keycloak_enabled or not issuer:
            raise ValueError("OIDC is not configured. Set KEYCLOAK_ENABLED and KEYCLOAK_ISSUER_URL.")

        client_id = os.getenv("KEYCLOAK_CLIENT_ID", "agenticai-web")
        redirect_uri = (
            redirect_uri_override
            or os.getenv(
                "KEYCLOAK_REDIRECT_URI",
                "http://localhost:3000/auth/oidc/callback",
            )
        )
        scope = os.getenv("KEYCLOAK_SCOPE", "openid profile email")

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

    async def handle_oidc_callback(
        self,
        code: str,
        state: str | None,
        response: Response,
        redirect_uri_override: str | None = None,
    ) -> dict[str, Any]:
        keycloak_enabled = os.getenv("KEYCLOAK_ENABLED", "false").lower() == "true"
        issuer = (os.getenv("KEYCLOAK_ISSUER_URL") or "").rstrip("/")
        client_id = os.getenv("KEYCLOAK_CLIENT_ID", "agenticai-web")
        client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")
        redirect_uri = (
            redirect_uri_override
            or os.getenv(
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

        # Keep cookie names aligned with existing dev tooling and proxy behavior.
        response.set_cookie(
            "fastapiusersauth",
            access_token,
            httponly=True,
            samesite="lax",
            max_age=expires_in,
            path="/",
        )
        response.set_cookie(
            "session",
            access_token,
            httponly=True,
            samesite="lax",
            max_age=expires_in,
            path="/",
        )
        if refresh_token:
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                samesite="lax",
                max_age=7 * 24 * 3600,
                path="/",
            )
        if id_token:
            response.set_cookie(
                "id_token",
                id_token,
                httponly=True,
                samesite="lax",
                max_age=expires_in,
                path="/",
            )

        redirect_url = state or "/"
        return {
            "success": True,
            "redirect_url": redirect_url,
            "oidc_expiry": datetime.now(UTC).isoformat(),
            "id_token": id_token,
        }

    async def get_mcp_servers(self) -> dict[str, Any]:
        mcp_servers = []
        tools_service_url = (
            os.getenv("TOOLS_SERVICE_URL")
            or os.getenv("MCP_SERVER_URL")
            or "http://localhost:8003"
        )

        if tools_service_url:
            mcp_servers.append(
                {
                    "id": 1,
                    "name": "Built-in Tools",
                    "description": "Built-in tools service",
                    "server_url": tools_service_url,
                    "owner": "system",
                    "is_authenticated": True,
                    "status": "CONNECTED",
                    "tool_count": 0,
                    "last_refreshed_at": datetime.now(UTC).isoformat(),
                }
            )

        return {"mcp_servers": mcp_servers}


_auth_metadata_controller: AuthMetadataController | None = None


def get_auth_metadata_controller() -> AuthMetadataController:
    """Get singleton AuthMetadataController."""
    global _auth_metadata_controller
    if _auth_metadata_controller is None:
        _auth_metadata_controller = AuthMetadataController()
    return _auth_metadata_controller
