import os
import time
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from jwt import PyJWKClient

from src.config import get_settings
from src.core.env import get_env

_env = get_env()
_settings = get_settings()

_JWKS_CLIENT: PyJWKClient | None = None


class KeycloakService:
    _admin_token_cache: str | None = None
    _admin_token_expires: float = 0
    _admin_token_cache_key: str | None = None

    @staticmethod
    def is_enabled() -> bool:
        return _env.KEYCLOAK_ENABLED or _settings.KEYCLOAK_ENABLED

    @staticmethod
    def has_admin_access() -> bool:
        """Whether the Keycloak admin REST API is accessible.

        This is a capability hint only. External Keycloak may still expose the
        admin REST API through the configured client's service account, but
        username/password admin credentials are intentionally ignored there.
        """
        if _env.EXTERNAL_KEYCLOAK or _settings.EXTERNAL_KEYCLOAK:
            return bool(KeycloakService().get_client_secret())
        return KeycloakService()._admin_credentials_configured() or bool(
            KeycloakService().get_client_secret()
        )

    def get_base_url(self) -> str:
        base_url = _env.KEYCLOAK_BASE_URL or _settings.KEYCLOAK_BASE_URL
        if base_url:
            return base_url.rstrip("/")

        issuer_url = _env.KEYCLOAK_ISSUER_URL or _settings.KEYCLOAK_ISSUER_URL
        if issuer_url:
            return issuer_url.rstrip("/").replace(f"/realms/{self.get_realm()}", "")

        raise ValueError("KEYCLOAK_BASE_URL or KEYCLOAK_ISSUER_URL must be configured")

    def get_realm(self) -> str:
        return _env.KEYCLOAK_REALM or _settings.KEYCLOAK_REALM

    def get_client_id(self) -> str:
        return _env.KEYCLOAK_CLIENT_ID or _settings.KEYCLOAK_CLIENT_ID or "agenticai-web"

    def get_client_secret(self) -> str | None:
        secret = _env.KEYCLOAK_CLIENT_SECRET or _settings.KEYCLOAK_CLIENT_SECRET
        return secret.strip() if secret and secret.strip() else None

    def _client_credentials_payload(self) -> dict[str, str]:
        payload = {"client_id": self.get_client_id()}
        client_secret = self.get_client_secret()
        if client_secret:
            payload["client_secret"] = client_secret
        return payload

    @staticmethod
    def is_external_keycloak() -> bool:
        return _env.EXTERNAL_KEYCLOAK or _settings.EXTERNAL_KEYCLOAK

    @staticmethod
    def _settings_field_was_configured(field_name: str) -> bool:
        return field_name in getattr(_settings, "model_fields_set", set())

    def _admin_credentials_configured(self) -> bool:
        if self.is_external_keycloak():
            return False
        username_configured = bool(
            _env.get("KEYCLOAK_ADMIN")
        ) or self._settings_field_was_configured("KEYCLOAK_ADMIN")
        password_configured = bool(
            _env.get("KEYCLOAK_ADMIN_PASSWORD")
        ) or self._settings_field_was_configured("KEYCLOAK_ADMIN_PASSWORD")
        return username_configured and password_configured

    def get_issuer_url(self) -> str | None:
        issuer = _env.KEYCLOAK_ISSUER_URL or _settings.KEYCLOAK_ISSUER_URL
        return issuer.rstrip("/") if issuer else None

    def _get_jwks_client(self) -> PyJWKClient | None:
        global _JWKS_CLIENT
        issuer = self.get_issuer_url()
        if not issuer:
            return None
        if _JWKS_CLIENT is None:
            jwks_url = f"{issuer}/protocol/openid-connect/certs"
            _JWKS_CLIENT = PyJWKClient(jwks_url, cache_keys=True)
        return _JWKS_CLIENT

    def _audiences(self) -> list[str]:
        raw = _env.KEYCLOAK_AUDIENCE or _settings.KEYCLOAK_AUDIENCE or ""
        audiences = [a.strip() for a in raw.split(",") if a.strip()]
        client_id = self.get_client_id()
        if client_id and client_id not in audiences:
            audiences.append(client_id)
        return audiences

    async def validate_token_jwks(self, token: str) -> dict[str, Any] | None:
        """Validate a Keycloak JWT using JWKS (local, no network call to userinfo).

        Returns the decoded claims on success, None otherwise.
        """
        jwks_client = self._get_jwks_client()
        if jwks_client is None:
            return None

        issuer = self.get_issuer_url()
        if not issuer:
            return None

        audiences = self._audiences()
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                jwt=token,
                key=signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                issuer=issuer,
                audience=audiences if audiences else None,
                leeway=int(os.environ.get("KEYCLOAK_TOKEN_LEEWAY_SECONDS", "120")),
                options={
                    "verify_aud": bool(audiences),
                    "verify_iss": True,
                    "verify_exp": True,
                },
            )
            return claims
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None

    async def _get_cached_admin_token(self, cache_key: str) -> str | None:
        if (
            self._admin_token_cache
            and self._admin_token_cache_key == cache_key
            and time.time() < self._admin_token_expires - 60
        ):
            return self._admin_token_cache
        return None

    def _cache_admin_token(self, cache_key: str, token_data: dict[str, Any]) -> str:
        self._admin_token_cache = str(token_data["access_token"])
        self._admin_token_cache_key = cache_key
        self._admin_token_expires = time.time() + token_data.get("expires_in", 300)
        return self._admin_token_cache

    async def _get_password_admin_token(self) -> str:
        cached = await self._get_cached_admin_token("password-admin")
        if cached:
            return cached
        admin_realm = "master"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{admin_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "username": _env.KEYCLOAK_ADMIN or _settings.KEYCLOAK_ADMIN,
                    "password": _env.KEYCLOAK_ADMIN_PASSWORD or _settings.KEYCLOAK_ADMIN_PASSWORD,
                    "client_id": "admin-cli",
                },
            )
            resp.raise_for_status()
            return self._cache_admin_token("password-admin", resp.json())

    async def _get_service_account_admin_token(self) -> str:
        if not self.get_client_secret():
            raise ValueError("Keycloak service account is not configured")
        cached = await self._get_cached_admin_token("service-account")
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    **self._client_credentials_payload(),
                },
            )
            resp.raise_for_status()
            return self._cache_admin_token("service-account", resp.json())

    async def _get_admin_token(self) -> str:
        if self.is_external_keycloak():
            return await self._get_service_account_admin_token()
        if self._admin_credentials_configured():
            return await self._get_password_admin_token()
        return await self._get_service_account_admin_token()

    async def _keycloak_request(
        self, method: str, path: str, token: str | None = None, **kwargs
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token or await self._get_admin_token()}"

        async with httpx.AsyncClient() as client:
            url = f"{self.get_base_url()}/admin/realms/{self.get_realm()}{path}"
            resp = await client.request(method, url, headers=headers, **kwargs)
            return resp

    async def get_user_profile(self, keycloak_id: str, token: str | None = None) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", f"/users/{keycloak_id}", token=token)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def list_users(
        self,
        first: int = 0,
        max: int = 1000,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", f"/users?first={first}&max={max}", token=token)
        resp.raise_for_status()
        return resp.json()

    async def get_user_by_email(
        self, email: str, token: str | None = None
    ) -> dict[str, Any] | None:
        resp = await self._keycloak_request(
            "GET",
            f"/users?email={quote(email)}&exact=true",
            token=token,
        )
        resp.raise_for_status()
        users = resp.json()
        return users[0] if users else None

    async def create_user(self, payload: dict[str, Any]) -> str | None:
        resp = await self._keycloak_request("POST", "/users", json=payload)
        if resp.status_code in (200, 201):
            location = resp.headers.get("Location")
            if location:
                return location.split("/")[-1]
        resp.raise_for_status()
        return None

    async def update_user(self, keycloak_id: str, payload: dict[str, Any]) -> bool:
        resp = await self._keycloak_request("PUT", f"/users/{keycloak_id}", json=payload)
        return resp.status_code in (200, 204)

    async def delete_user(self, keycloak_id: str) -> bool:
        resp = await self._keycloak_request("DELETE", f"/users/{keycloak_id}")
        return resp.status_code in (200, 204)

    async def set_password(self, keycloak_id: str, password: str, temporary: bool = False) -> bool:
        resp = await self._keycloak_request(
            "PUT",
            f"/users/{keycloak_id}/reset-password",
            json={
                "type": "password",
                "value": password,
                "temporary": temporary,
            },
        )
        return resp.status_code in (200, 204)

    async def get_realm_role(
        self, role_name: str, token: str | None = None
    ) -> dict[str, Any] | None:
        resp = await self._keycloak_request("GET", f"/roles/{role_name}", token=token)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def create_realm_role(self, role_name: str, description: str | None = None) -> bool:
        resp = await self._keycloak_request(
            "POST",
            "/roles",
            json={
                "name": role_name,
                "description": description or f"AgenticAI {role_name} role",
            },
        )
        return resp.status_code in (200, 201, 204, 409)

    async def get_realm_roles(self, token: str | None = None) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", "/roles", token=token)
        resp.raise_for_status()
        return resp.json()

    async def set_realm_role(self, keycloak_id: str, role_name: str) -> bool:
        role = await self.get_realm_role(role_name)
        if not role:
            await self.create_realm_role(role_name)
            role = await self.get_realm_role(role_name)
            if not role:
                return False

        current_roles_resp = await self._keycloak_request(
            "GET", f"/users/{keycloak_id}/role-mappings/realm"
        )
        current_roles = current_roles_resp.json()
        roles_to_remove = [r for r in current_roles if r["name"] != role_name]

        if roles_to_remove:
            await self._keycloak_request(
                "DELETE", f"/users/{keycloak_id}/role-mappings/realm", json=roles_to_remove
            )

        await self._keycloak_request(
            "POST", f"/users/{keycloak_id}/role-mappings/realm", json=[role]
        )
        return True

    async def get_user_realm_roles(
        self,
        keycloak_id: str,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        resp = await self._keycloak_request(
            "GET",
            f"/users/{keycloak_id}/role-mappings/realm",
            token=token,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_user_info(self, access_token: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            return resp.json()

    async def get_oidc_authorize_url(self, redirect_uri: str, state: str | None = None) -> str:
        client_id = self.get_client_id()
        base_url = self.get_base_url()
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
        }
        if state:
            params["state"] = state
        import urllib.parse

        return f"{base_url}/realms/{self.get_realm()}/protocol/openid-connect/auth?{urllib.parse.urlencode(params)}"

    async def handle_oidc_callback(
        self,
        code: str,
        redirect_uri: str,
        fallback_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            token_url = (
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token"
            )

            def _payload(uri: str) -> dict[str, str]:
                return {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": uri,
                    **self._client_credentials_payload(),
                }

            async def _extract_error_detail(response: httpx.Response) -> str:
                """Extract error detail from Keycloak error response."""
                try:
                    error_body = response.json()
                    if isinstance(error_body, dict):
                        # Keycloak returns error + error_description
                        if error_body.get("error_description"):
                            return error_body["error_description"]
                        if error_body.get("error"):
                            return error_body["error"]
                except Exception:
                    pass
                return f"Keycloak token exchange failed (status {response.status_code})"

            resp = await client.post(token_url, data=_payload(redirect_uri))
            if resp.is_success:
                return resp.json()

            # Some frontend flows attach a post-login redirect URI in query params,
            # which can differ from the actual callback URI used for the auth code.
            # Retry with the concrete callback URL when available.
            if fallback_redirect_uri and fallback_redirect_uri != redirect_uri:
                fallback_resp = await client.post(token_url, data=_payload(fallback_redirect_uri))
                if fallback_resp.is_success:
                    return fallback_resp.json()
                resp = fallback_resp  # Use fallback response for error details

            # Both attempts failed - extract error detail
            error_detail = await _extract_error_detail(resp)
            raise ValueError(error_detail)

    async def password_grant(self, username: str, password: str) -> dict[str, Any]:
        """Direct Access Grant — authenticate with username/password against Keycloak.

        POSTs to Keycloak's token endpoint with grant_type=password.
        Returns Keycloak token payload { access_token, refresh_token, id_token, expires_in, token_type }.
        Raises ValueError on authentication failure.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    **self._client_credentials_payload(),
                    "username": username,
                    "password": password,
                    "scope": "openid profile email",
                },
            )
            if resp.is_success:
                return resp.json()

            try:
                error_body = resp.json()
                if isinstance(error_body, dict):
                    detail = (
                        error_body.get("error_description")
                        or error_body.get("error")
                        or f"Authentication failed (status {resp.status_code})"
                    )
            except Exception:
                detail = f"Authentication failed (status {resp.status_code})"
            raise ValueError(detail)

    async def refresh_token_grant(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new set of tokens from Keycloak.

        POSTs to Keycloak's token endpoint with grant_type=refresh_token.
        Returns { access_token, refresh_token, id_token, expires_in, token_type }.
        Raises ValueError on authentication failure.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "refresh_token",
                    **self._client_credentials_payload(),
                    "refresh_token": refresh_token,
                },
            )
            if resp.is_success:
                return resp.json()

            try:
                error_body = resp.json()
                if isinstance(error_body, dict):
                    detail = (
                        error_body.get("error_description")
                        or error_body.get("error")
                        or f"Token refresh failed (status {resp.status_code})"
                    )
            except Exception:
                detail = f"Token refresh failed (status {resp.status_code})"
            raise ValueError(detail)

    async def backchannel_logout(
        self, refresh_token: str | None = None, id_token_hint: str | None = None
    ) -> bool:
        async with httpx.AsyncClient() as client:
            data = {}
            if refresh_token:
                data["refresh_token"] = refresh_token
            if id_token_hint:
                data["id_token_hint"] = id_token_hint
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/logout",
                data={**data, **self._client_credentials_payload()},
            )
            return resp.status_code in (200, 204, 400)


_keycloak_service = KeycloakService()


def get_keycloak_service() -> KeycloakService:
    return _keycloak_service
