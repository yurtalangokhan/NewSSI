from typing import Any

import httpx

from src.config import get_settings
from src.core.env import get_env

_env = get_env()
_settings = get_settings()


class KeycloakService:
    _admin_token_cache: dict | None = None
    _admin_token_expires: float = 0

    @staticmethod
    def is_enabled() -> bool:
        return _env.KEYCLOAK_ENABLED

    def get_base_url(self) -> str:
        return _env.KEYCLOAK_BASE_URL or f"{_env.KEYCLOAK_ISSUER_URL}/".replace(f"/realms/{_env.KEYCLOAK_REALM}/", "/")

    def get_realm(self) -> str:
        return _env.KEYCLOAK_REALM

    async def _get_admin_token(self) -> str:
        import time
        if self._admin_token_cache and time.time() < self._admin_token_expires - 60:
            return self._admin_token_cache

        admin_realm = "master"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{admin_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "username": _env.KEYCLOAK_ADMIN,
                    "password": _env.KEYCLOAK_ADMIN_PASSWORD,
                    "client_id": "admin-cli",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._admin_token_cache = data["access_token"]
            self._admin_token_expires = time.time() + data.get("expires_in", 300)
            return self._admin_token_cache

    async def _keycloak_request(self, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif method in ("POST", "PUT", "DELETE"):
            headers["Authorization"] = f"Bearer {await self._get_admin_token()}"

        async with httpx.AsyncClient() as client:
            url = f"{self.get_base_url()}/admin/realms/{self.get_realm()}{path}"
            resp = await client.request(method, url, headers=headers, **kwargs)
            return resp

    async def get_user_profile(self, keycloak_id: str) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", f"/users/{keycloak_id}")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def list_users(self, first: int = 0, max: int = 1000) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", f"/users?first={first}&max={max}")
        resp.raise_for_status()
        return resp.json()

    async def create_user(self, payload: dict[str, Any]) -> str | None:
        resp = await self._keycloak_request("POST", "/users", json=payload)
        if resp.status_code in (200, 201):
            location = resp.headers.get("Location")
            if location:
                return location.split("/")[-1]
        return None

    async def update_user(self, keycloak_id: str, payload: dict[str, Any]) -> bool:
        resp = await self._keycloak_request("PUT", f"/users/{keycloak_id}", json=payload)
        return resp.status_code in (200, 204)

    async def delete_user(self, keycloak_id: str) -> bool:
        resp = await self._keycloak_request("DELETE", f"/users/{keycloak_id}")
        return resp.status_code in (200, 204)

    async def set_password(self, keycloak_id: str, password: str, temporary: bool = False) -> bool:
        resp = await self._keycloak_request("PUT", f"/users/{keycloak_id}/reset-password", json={
            "type": "password",
            "value": password,
            "temporary": temporary,
        })
        return resp.status_code in (200, 204)

    async def get_realm_role(self, role_name: str) -> dict[str, Any] | None:
        resp = await self._keycloak_request("GET", f"/roles/{role_name}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def get_realm_roles(self) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", "/roles")
        resp.raise_for_status()
        return resp.json()

    async def set_realm_role(self, keycloak_id: str, role_name: str) -> bool:
        role = await self.get_realm_role(role_name)
        if not role:
            return False

        current_roles_resp = await self._keycloak_request("GET", f"/users/{keycloak_id}/role-mappings/realm")
        current_roles = current_roles_resp.json()
        supported = ["admin", "global_curator", "curator", "limited", "basic"]
        roles_to_remove = [r for r in current_roles if r["name"] in supported]

        if roles_to_remove:
            await self._keycloak_request("DELETE", f"/users/{keycloak_id}/role-mappings/realm", json=roles_to_remove)

        await self._keycloak_request("POST", f"/users/{keycloak_id}/role-mappings/realm", json=[role])
        return True

    async def get_user_realm_roles(self, keycloak_id: str) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", f"/users/{keycloak_id}/role-mappings/realm")
        resp.raise_for_status()
        return resp.json()

    async def get_oidc_authorize_url(self, redirect_uri: str, state: str | None = None) -> str:
        client_id = _env.KEYCLOAK_CLIENT_ID or "agenticai-web"
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
            client_id = _env.KEYCLOAK_CLIENT_ID or "agenticai-web"
            token_url = f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token"

            def _payload(uri: str) -> dict[str, str]:
                return {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": uri,
                    "client_id": client_id,
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

    async def backchannel_logout(self, refresh_token: str | None = None, id_token_hint: str | None = None) -> bool:
        async with httpx.AsyncClient() as client:
            data = {}
            if refresh_token:
                data["refresh_token"] = refresh_token
            if id_token_hint:
                data["id_token_hint"] = id_token_hint
            client_id = _env.KEYCLOAK_CLIENT_ID or "agenticai-web"
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/logout",
                data={**data, "client_id": client_id},
            )
            return resp.status_code in (200, 204, 400)


_keycloak_service = KeycloakService()


def get_keycloak_service() -> KeycloakService:
    return _keycloak_service
