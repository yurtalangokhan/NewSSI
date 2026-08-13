import fnmatch
import time
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import jwt
from i18n import t
from jwt import PyJWKClient

from src.config import get_settings
from src.core.env import get_env
from src.service.keycloak_broker import KeycloakBrokerMixin

_env = get_env()
_settings = get_settings()

_JWKS_CLIENT: PyJWKClient | None = None


class KeycloakService(KeycloakBrokerMixin):
    _runtime_settings: dict[str, Any] = {}
    _admin_token_cache: str | None = None
    _admin_token_expires: float = 0
    _admin_token_cache_key: str | None = None
    _client_uuid_cache: str | None = None
    _client_uuid_cache_key: str | None = None

    @classmethod
    def set_runtime_settings(cls, settings: dict[str, Any]) -> None:
        cls._runtime_settings = {
            key: value for key, value in settings.items() if value is not None and value != ""
        }
        cls._admin_token_cache = None
        cls._admin_token_expires = 0
        cls._admin_token_cache_key = None
        cls._client_uuid_cache = None
        cls._client_uuid_cache_key = None

    @classmethod
    def _runtime_value(cls, key: str) -> Any:
        return cls._runtime_settings.get(key)

    @classmethod
    def _bool_config(cls, key: str, fallback: bool) -> bool:
        value = cls._runtime_value(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return fallback

    @classmethod
    def _str_config(cls, key: str, fallback: str | None = None) -> str | None:
        value = cls._runtime_value(key)
        if value is None:
            return fallback
        text = str(value).strip()
        return text or fallback

    @classmethod
    def _env_bool_config(cls, key: str) -> bool | None:
        value = _env.get(key)
        if value is None:
            return None
        return str(value).lower() == "true"

    @classmethod
    def _env_str_config(cls, key: str) -> str | None:
        value = _env.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _external_bool_config(cls, key: str, fallback: bool) -> bool:
        env_value = cls._env_bool_config(key)
        if env_value is not None:
            return env_value
        return cls._bool_config(key, fallback)

    @classmethod
    def _external_str_config(cls, key: str, fallback: str | None = None) -> str | None:
        env_value = cls._env_str_config(key)
        if env_value is not None:
            return env_value
        return cls._str_config(key, fallback)

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._bool_config(
            "KEYCLOAK_ENABLED", _env.KEYCLOAK_ENABLED or _settings.KEYCLOAK_ENABLED
        )

    @staticmethod
    def has_admin_access() -> bool:
        """Whether the Keycloak admin REST API is accessible.

        This is a capability hint only. Internal Keycloak exposes the
        admin REST API through the configured client's service account.
        """
        return KeycloakService()._admin_credentials_configured() or bool(
            KeycloakService().get_client_secret()
        )

    def get_base_url(self) -> str:
        base_url = self._str_config(
            "KEYCLOAK_BASE_URL",
            _env.KEYCLOAK_BASE_URL or _settings.KEYCLOAK_BASE_URL,
        )
        if base_url:
            return base_url.rstrip("/")

        issuer_url = self._str_config(
            "KEYCLOAK_ISSUER_URL",
            _env.KEYCLOAK_ISSUER_URL or _settings.KEYCLOAK_ISSUER_URL,
        )
        if issuer_url:
            return issuer_url.rstrip("/").replace(f"/realms/{self.get_realm()}", "")

        raise ValueError(t("keycloak.base_url_not_configured"))

    def get_realm(self) -> str:
        return (
            self._str_config("KEYCLOAK_REALM", _env.KEYCLOAK_REALM or _settings.KEYCLOAK_REALM)
            or "agenticai"
        )

    def get_client_id(self) -> str:
        return (
            self._str_config(
                "KEYCLOAK_CLIENT_ID",
                _env.KEYCLOAK_CLIENT_ID or _settings.KEYCLOAK_CLIENT_ID,
            )
            or "agenticai-web"
        )

    def get_login_client_id(self) -> str:
        """Client ID used for Direct Access Grant (password) login.
        Uses a separate public client (agenticai-web) that has directAccessGrantsEnabled=true."""
        return (
            self._str_config(
                "KEYCLOAK_LOGIN_CLIENT_ID",
                _env.KEYCLOAK_LOGIN_CLIENT_ID or _settings.KEYCLOAK_LOGIN_CLIENT_ID,
            )
            or "agenticai-web"
        )

    def get_client_secret(self) -> str | None:
        secret = self._str_config(
            "KEYCLOAK_CLIENT_SECRET",
            _env.KEYCLOAK_CLIENT_SECRET or _settings.KEYCLOAK_CLIENT_SECRET,
        )
        return secret.strip() if secret and secret.strip() else None

    def get_oidc_redirect_uri(self) -> str:
        redirect_uri = self._str_config(
            "KEYCLOAK_REDIRECT_URI",
            _env.KEYCLOAK_REDIRECT_URI or _settings.KEYCLOAK_REDIRECT_URI,
        )
        if redirect_uri and "*" not in redirect_uri:
            return redirect_uri

        for candidate in self._login_client_redirect_uris():
            if "*" not in candidate:
                return candidate

            parsed = urlparse(candidate)
            if parsed.scheme and parsed.netloc:
                wildcard_base = candidate.split("*", 1)[0].rstrip("/")
                return f"{wildcard_base}/auth/oidc/callback"

        raise ValueError(t("keycloak.redirect_uri_not_absolute"))

    def is_external_keycloak(self) -> bool:
        return self._external_bool_config(
            "EXTERNAL_KEYCLOAK",
            _env.EXTERNAL_KEYCLOAK or _settings.EXTERNAL_KEYCLOAK,
        )

    def _client_credentials_payload(self) -> dict[str, str]:
        payload = {"client_id": self.get_client_id()}
        client_secret = self.get_client_secret()
        if client_secret:
            payload["client_secret"] = client_secret
        return payload

    @staticmethod
    def _settings_field_was_configured(field_name: str) -> bool:
        return field_name in getattr(_settings, "model_fields_set", set())

    def _admin_credentials_configured(self) -> bool:
        username_configured = bool(
            self._str_config("KEYCLOAK_ADMIN", _env.get("KEYCLOAK_ADMIN"))
        ) or self._settings_field_was_configured("KEYCLOAK_ADMIN")
        password_configured = bool(
            self._str_config("KEYCLOAK_ADMIN_PASSWORD", _env.get("KEYCLOAK_ADMIN_PASSWORD"))
        ) or self._settings_field_was_configured("KEYCLOAK_ADMIN_PASSWORD")
        return username_configured and password_configured

    def get_issuer_url(self) -> str | None:
        issuer = self._str_config(
            "KEYCLOAK_ISSUER_URL",
            _env.KEYCLOAK_ISSUER_URL or _settings.KEYCLOAK_ISSUER_URL,
        )
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
        raw = (
            self._str_config(
                "KEYCLOAK_AUDIENCE",
                _env.KEYCLOAK_AUDIENCE or _settings.KEYCLOAK_AUDIENCE,
            )
            or ""
        )
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
                leeway=_env.KEYCLOAK_TOKEN_LEEWAY_SECONDS,
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
                    "username": self._str_config(
                        "KEYCLOAK_ADMIN",
                        _env.KEYCLOAK_ADMIN or _settings.KEYCLOAK_ADMIN,
                    ),
                    "password": self._str_config(
                        "KEYCLOAK_ADMIN_PASSWORD",
                        _env.KEYCLOAK_ADMIN_PASSWORD or _settings.KEYCLOAK_ADMIN_PASSWORD,
                    ),
                    "client_id": "admin-cli",
                },
            )
            resp.raise_for_status()
            return self._cache_admin_token("password-admin", resp.json())

    async def _get_service_account_admin_token(self) -> str:
        if not self.get_client_secret():
            raise ValueError(t("keycloak.service_account_not_configured"))
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

    async def get_realm_configuration(self) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", "")
        resp.raise_for_status()
        return resp.json()

    async def update_realm_configuration(self, updates: dict[str, Any]) -> dict[str, Any]:
        realm_config = await self.get_realm_configuration()
        payload = {**realm_config, **updates}
        resp = await self._keycloak_request("PUT", "", json=payload)
        if resp.status_code not in (200, 204):
            resp.raise_for_status()
        return await self.get_realm_configuration()

    async def get_user_profile(self, keycloak_id: str, token: str | None = None) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", f"/users/{keycloak_id}", token=token)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    def get_external_keycloak_alias(self) -> str:
        alias = self._external_str_config(
            "EXTERNAL_KEYCLOAK_ALIAS",
            _env.EXTERNAL_KEYCLOAK_ALIAS or _settings.EXTERNAL_KEYCLOAK_ALIAS,
        )
        return alias.strip() or "external-keycloak"

    def _external_issuer_url(self) -> str:
        issuer = self._external_str_config(
            "EXTERNAL_KEYCLOAK_ISSUER_URL",
            _env.EXTERNAL_KEYCLOAK_ISSUER_URL or _settings.EXTERNAL_KEYCLOAK_ISSUER_URL,
        )
        if issuer:
            return issuer.rstrip("/")

        base_url = self._external_str_config(
            "EXTERNAL_KEYCLOAK_BASE_URL",
            _env.EXTERNAL_KEYCLOAK_BASE_URL or _settings.EXTERNAL_KEYCLOAK_BASE_URL,
        )
        realm = self._external_str_config(
            "EXTERNAL_KEYCLOAK_REALM",
            _env.EXTERNAL_KEYCLOAK_REALM or _settings.EXTERNAL_KEYCLOAK_REALM,
        )
        if not base_url or not realm:
            raise ValueError(t("keycloak.external_issuer_not_configured"))
        return f"{base_url.rstrip('/')}/realms/{realm}"

    def get_external_issuer_url(self) -> str:
        return self._external_issuer_url()

    def _external_backend_issuer_url(self) -> str:
        issuer = self._external_str_config(
            "EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL",
            _env.EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL
            or _settings.EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL,
        )
        return issuer.rstrip("/") if issuer else self._external_issuer_url()

    def get_external_broker_redirect_uri(self) -> str:
        return (
            f"{self.get_base_url()}/realms/{self.get_realm()}/broker/"
            f"{self.get_external_keycloak_alias()}/endpoint"
        )

    def _external_admin_credentials_configured(self) -> bool:
        return bool(
            self._external_str_config(
                "EXTERNAL_KEYCLOAK_ADMIN",
                _env.EXTERNAL_KEYCLOAK_ADMIN or _settings.EXTERNAL_KEYCLOAK_ADMIN,
            )
            and self._external_str_config(
                "EXTERNAL_KEYCLOAK_ADMIN_PASSWORD",
                _env.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD or _settings.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD,
            )
        )

    async def _get_external_admin_token(self) -> str:
        cached = await self._get_cached_admin_token("external-password-admin")
        if cached:
            return cached

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._external_backend_issuer_url().rsplit('/realms/', 1)[0]}"
                "/realms/master/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "username": self._external_str_config(
                        "EXTERNAL_KEYCLOAK_ADMIN",
                        _env.EXTERNAL_KEYCLOAK_ADMIN or _settings.EXTERNAL_KEYCLOAK_ADMIN,
                    ),
                    "password": self._external_str_config(
                        "EXTERNAL_KEYCLOAK_ADMIN_PASSWORD",
                        _env.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD
                        or _settings.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD,
                    ),
                    "client_id": "admin-cli",
                },
            )
            resp.raise_for_status()
            return self._cache_admin_token("external-password-admin", resp.json())

    async def _external_keycloak_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {await self._get_external_admin_token()}"
        external_realm = self._external_str_config(
            "EXTERNAL_KEYCLOAK_REALM",
            _env.EXTERNAL_KEYCLOAK_REALM or _settings.EXTERNAL_KEYCLOAK_REALM,
        )
        if not external_realm:
            raise ValueError(t("keycloak.external_realm_not_configured"))

        async with httpx.AsyncClient() as client:
            base_url = self._external_backend_issuer_url().rsplit("/realms/", 1)[0]
            return await client.request(
                method,
                f"{base_url}/admin/realms/{external_realm}{path}",
                headers=headers,
                **kwargs,
            )

    def _external_idp_payload(self) -> dict[str, Any]:
        client_id = self._external_str_config(
            "EXTERNAL_KEYCLOAK_CLIENT_ID",
            _env.EXTERNAL_KEYCLOAK_CLIENT_ID or _settings.EXTERNAL_KEYCLOAK_CLIENT_ID,
        )
        client_secret = self._external_str_config(
            "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
            _env.EXTERNAL_KEYCLOAK_CLIENT_SECRET or _settings.EXTERNAL_KEYCLOAK_CLIENT_SECRET,
        )
        if not client_id:
            raise ValueError(t("keycloak.external_client_id_not_configured"))
        if not client_secret:
            raise ValueError(t("keycloak.external_client_secret_not_configured"))

        alias = self.get_external_keycloak_alias()
        issuer = self._external_issuer_url()
        backend_issuer = self._external_backend_issuer_url()
        display_name = (
            self._external_str_config(
                "EXTERNAL_KEYCLOAK_DISPLAY_NAME",
                _env.EXTERNAL_KEYCLOAK_DISPLAY_NAME or _settings.EXTERNAL_KEYCLOAK_DISPLAY_NAME,
            )
            or alias
        )
        return {
            "alias": alias,
            "displayName": display_name,
            "providerId": "keycloak-oidc",
            "enabled": True,
            "trustEmail": True,
            "storeToken": True,
            "addReadTokenRoleOnCreate": False,
            "authenticateByDefault": False,
            "linkOnly": False,
            "firstBrokerLoginFlowAlias": "first broker login",
            "config": {
                "clientId": client_id,
                "clientSecret": client_secret,
                "clientAuthMethod": "client_secret_post",
                "authorizationUrl": f"{issuer}/protocol/openid-connect/auth",
                "tokenUrl": f"{backend_issuer}/protocol/openid-connect/token",
                "userInfoUrl": f"{backend_issuer}/protocol/openid-connect/userinfo",
                "jwksUrl": f"{backend_issuer}/protocol/openid-connect/certs",
                "issuer": issuer,
                "defaultScope": "openid profile email",
                "syncMode": "FORCE",
                "validateSignature": "true",
                "useJwksUrl": "true",
            },
        }

    @staticmethod
    def _csv_values(raw: str | None) -> list[str]:
        return [value.strip() for value in (raw or "").split(",") if value.strip()]

    @staticmethod
    def _merge_unique_values(existing: list[Any], configured: list[str]) -> list[str]:
        merged: list[str] = []
        for value in [*existing, *configured]:
            if not isinstance(value, str):
                continue
            item = value.strip()
            if item and item not in merged:
                merged.append(item)
        return merged

    @staticmethod
    def _value_matches_pattern(value: str, patterns: list[str]) -> bool:
        return any(pattern in ("*", "+") or fnmatch.fnmatchcase(value, pattern) for pattern in patterns)

    @staticmethod
    def _origin_from_url(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _post_logout_redirect_values(raw: Any) -> list[str]:
        values = raw if isinstance(raw, list) else str(raw or "").split("##")
        return [value.strip() for value in values if isinstance(value, str) and value.strip()]

    @classmethod
    def _merge_post_logout_redirect_uris(cls, existing: Any, configured: str) -> str:
        return "##".join(
            cls._merge_unique_values(
                cls._post_logout_redirect_values(existing),
                cls._post_logout_redirect_values(configured),
            )
        )

    def _login_client_redirect_uris(self) -> list[str]:
        raw = self._str_config(
            "KEYCLOAK_REDIRECT_URIS",
            _env.KEYCLOAK_REDIRECT_URIS
            or _settings.KEYCLOAK_REDIRECT_URIS
            or _env.KEYCLOAK_REDIRECT_URI
            or _settings.KEYCLOAK_REDIRECT_URI,
        )
        return self._csv_values(raw) or ["*"]

    def _login_client_web_origins(self) -> list[str]:
        raw = self._str_config(
            "KEYCLOAK_WEB_ORIGINS",
            _env.KEYCLOAK_WEB_ORIGINS or _settings.KEYCLOAK_WEB_ORIGINS,
        )
        return self._csv_values(raw) or ["+"]

    def _login_client_post_logout_redirect_uris(self) -> str:
        return (
            self._str_config(
                "KEYCLOAK_POST_LOGOUT_REDIRECT_URIS",
                _env.KEYCLOAK_POST_LOGOUT_REDIRECT_URIS
                or _settings.KEYCLOAK_POST_LOGOUT_REDIRECT_URIS,
            )
            or "+"
        )

    async def ensure_login_client_config(self) -> dict[str, Any]:
        """Ensure the SP login client can issue gateway-accepted tokens.

        /auth/ee/login submits username/password to user-service, which uses
        Keycloak's password grant against the SP realm. Therefore this client
        must have Direct Access Grants enabled and must be configured as a
        public frontend client.
        """
        client_id = self.get_login_client_id()
        try:
            client_uuid = await self.get_client_uuid(client_id=client_id)
            resp = await self._keycloak_request("GET", f"/clients/{client_uuid}")
            resp.raise_for_status()
            current = resp.json()
            if not isinstance(current, dict):
                raise ValueError(t("keycloak.client_response_invalid", client_id=client_id))
            action = "updated"
        except ValueError:
            current = {
                "clientId": client_id,
                "name": client_id,
                "protocol": "openid-connect",
                "attributes": {},
            }
            action = "created"

        attributes = dict(current.get("attributes") or {})
        attributes["post.logout.redirect.uris"] = self._merge_post_logout_redirect_uris(
            attributes.get("post.logout.redirect.uris"),
            self._login_client_post_logout_redirect_uris(),
        )
        payload = {
            **current,
            "clientId": client_id,
            "name": current.get("name") or client_id,
            "protocol": "openid-connect",
            "enabled": True,
            "publicClient": True,
            "bearerOnly": False,
            "standardFlowEnabled": True,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": False,
            "redirectUris": self._merge_unique_values(
                list(current.get("redirectUris") or []),
                self._login_client_redirect_uris(),
            ),
            "webOrigins": self._merge_unique_values(
                list(current.get("webOrigins") or []),
                self._login_client_web_origins(),
            ),
            "attributes": attributes,
        }
        payload.pop("secret", None)

        if action == "created":
            create_resp = await self._keycloak_request("POST", "/clients", json=payload)
            if create_resp.status_code not in (200, 201, 204, 409):
                create_resp.raise_for_status()
            if create_resp.status_code == 409:
                action = "updated"
                client_uuid = await self.get_client_uuid(client_id=client_id)
                update_resp = await self._keycloak_request(
                    "PUT",
                    f"/clients/{client_uuid}",
                    json=payload,
                )
                if update_resp.status_code not in (200, 204):
                    update_resp.raise_for_status()
            else:
                self._client_uuid_cache = None
                self._client_uuid_cache_key = None
        else:
            update_resp = await self._keycloak_request(
                "PUT",
                f"/clients/{client_uuid}",
                json=payload,
            )
            if update_resp.status_code not in (200, 204):
                update_resp.raise_for_status()

        return {
            "status": action,
            "client_id": client_id,
            "direct_access_grants_enabled": True,
            "public_client": True,
            "redirect_uris": payload["redirectUris"],
            "web_origins": payload["webOrigins"],
        }

    async def ensure_login_client_redirect_uri(
        self,
        redirect_uri: str | None,
        post_logout_redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        if not redirect_uri:
            return {"status": "skipped", "reason": "redirect_uri is not set"}

        web_origin = self._origin_from_url(redirect_uri)
        if web_origin is None:
            return {
                "status": "skipped",
                "reason": "redirect_uri is not an absolute HTTP(S) URL",
                "redirect_uri": redirect_uri,
            }

        client_id = self.get_login_client_id()
        client_uuid = await self.get_client_uuid(client_id=client_id)
        resp = await self._keycloak_request("GET", f"/clients/{client_uuid}")
        resp.raise_for_status()
        current = resp.json()
        if not isinstance(current, dict):
            raise ValueError(t("keycloak.client_response_invalid", client_id=client_id))

        current_redirect_uris = self._merge_unique_values(
            list(current.get("redirectUris") or []), []
        )
        current_web_origins = self._merge_unique_values(list(current.get("webOrigins") or []), [])
        attributes = dict(current.get("attributes") or {})
        current_post_logout_redirect_uris = self._post_logout_redirect_values(
            attributes.get("post.logout.redirect.uris")
        )
        redirect_exists = self._value_matches_pattern(redirect_uri, current_redirect_uris)
        origin_exists = self._value_matches_pattern(web_origin, current_web_origins)
        post_logout_exists = (
            not post_logout_redirect_uri
            or post_logout_redirect_uri in current_post_logout_redirect_uris
            or self._value_matches_pattern(
                post_logout_redirect_uri,
                [
                    uri
                    for uri in current_post_logout_redirect_uris
                    if uri != "+"
                ],
            )
        )

        if redirect_exists and origin_exists and post_logout_exists:
            return {
                "status": "exists",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "web_origin": web_origin,
            }

        if post_logout_redirect_uri and not post_logout_exists:
            attributes["post.logout.redirect.uris"] = "##".join(
                [*current_post_logout_redirect_uris, post_logout_redirect_uri]
            )

        payload = {
            **current,
            "redirectUris": current_redirect_uris
            if redirect_exists
            else [*current_redirect_uris, redirect_uri],
            "webOrigins": current_web_origins
            if origin_exists
            else [*current_web_origins, web_origin],
            "attributes": attributes,
        }
        payload.pop("secret", None)
        update_resp = await self._keycloak_request("PUT", f"/clients/{client_uuid}", json=payload)
        if update_resp.status_code not in (200, 204):
            update_resp.raise_for_status()

        return {
            "status": "updated",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "web_origin": web_origin,
        }

    async def ensure_external_identity_provider(self) -> dict[str, Any]:
        if not self.is_external_keycloak():
            return {"status": "skipped", "reason": "EXTERNAL_KEYCLOAK is disabled"}

        alias = self.get_external_keycloak_alias()
        payload = self._external_idp_payload()

        existing_resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}",
        )
        if existing_resp.status_code == 404:
            resp = await self._keycloak_request(
                "POST",
                "/identity-provider/instances",
                json=payload,
            )
            if resp.status_code not in (200, 201, 204, 409):
                resp.raise_for_status()
            action = "created"
        else:
            existing_resp.raise_for_status()
            resp = await self._keycloak_request(
                "PUT",
                f"/identity-provider/instances/{quote(alias, safe='')}",
                json=payload,
            )
            if resp.status_code not in (200, 204):
                resp.raise_for_status()
            action = "updated"

        default_role_result = await self._ensure_enduser_default_realm_role()
        mapper_result = await self._remove_external_enduser_mapper(alias)
        groups_mapper_result = await self._ensure_external_groups_mappers(alias)
        external_client_result = await self.ensure_external_client_redirect_uri()
        return {
            "status": action,
            "alias": alias,
            "default_role": default_role_result,
            "external_client": external_client_result,
            "mapper": mapper_result,
            "groups_mapper": groups_mapper_result,
        }

    async def ensure_external_client_redirect_uri(self) -> dict[str, Any]:
        if not self.is_external_keycloak():
            return {"status": "skipped", "reason": "EXTERNAL_KEYCLOAK is disabled"}

        required_redirect_uri = self.get_external_broker_redirect_uri()
        external_client_id = self._external_str_config(
            "EXTERNAL_KEYCLOAK_CLIENT_ID",
            _env.EXTERNAL_KEYCLOAK_CLIENT_ID or _settings.EXTERNAL_KEYCLOAK_CLIENT_ID,
        )
        if not external_client_id:
            return {"status": "skipped", "reason": "EXTERNAL_KEYCLOAK_CLIENT_ID is not set"}
        if not self._external_admin_credentials_configured():
            return {
                "status": "skipped",
                "reason": "EXTERNAL_KEYCLOAK_ADMIN credentials are not configured",
                "client_id": external_client_id,
                "required_redirect_uri": required_redirect_uri,
            }

        resp = await self._external_keycloak_request(
            "GET",
            f"/clients?clientId={quote(external_client_id)}",
        )
        resp.raise_for_status()
        clients = resp.json()
        if not isinstance(clients, list) or not clients:
            return {
                "status": "skipped",
                "reason": "external Keycloak client was not found",
                "client_id": external_client_id,
                "required_redirect_uri": required_redirect_uri,
            }

        client = clients[0]
        client_uuid = client.get("id")
        if not client_uuid:
            return {
                "status": "skipped",
                "reason": "external Keycloak client response has no id",
                "client_id": external_client_id,
                "required_redirect_uri": required_redirect_uri,
            }

        client_resp = await self._external_keycloak_request("GET", f"/clients/{client_uuid}")
        client_resp.raise_for_status()
        payload = client_resp.json()
        redirect_uris = list(payload.get("redirectUris") or [])
        if required_redirect_uri in redirect_uris:
            return {
                "status": "exists",
                "client_id": external_client_id,
                "required_redirect_uri": required_redirect_uri,
            }

        redirect_uris.append(required_redirect_uri)
        payload["redirectUris"] = redirect_uris
        update_resp = await self._external_keycloak_request(
            "PUT",
            f"/clients/{client_uuid}",
            json=payload,
        )
        if update_resp.status_code not in (200, 204):
            update_resp.raise_for_status()

        return {
            "status": "updated",
            "client_id": external_client_id,
            "required_redirect_uri": required_redirect_uri,
        }

    async def get_external_identity_provider_status(self) -> dict[str, Any]:
        alias = self.get_external_keycloak_alias()
        configured = self.is_external_keycloak()
        status: dict[str, Any] = {
            "enabled": configured,
            "alias": alias,
            "exists": False,
            "reachable": False,
            "provider": None,
            "mapper": None,
            "default_role": None,
        }
        if not self.is_enabled():
            status["error"] = "KEYCLOAK_ENABLED is disabled"
            return status
        if not configured:
            status["error"] = "EXTERNAL_KEYCLOAK is disabled"
            return status

        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}",
        )
        status["reachable"] = True
        if resp.status_code == 404:
            return status
        resp.raise_for_status()

        provider = resp.json()
        status["exists"] = True
        status["provider"] = {
            "alias": provider.get("alias"),
            "displayName": provider.get("displayName"),
            "providerId": provider.get("providerId"),
            "enabled": provider.get("enabled"),
            "trustEmail": provider.get("trustEmail"),
            "firstBrokerLoginFlowAlias": provider.get("firstBrokerLoginFlowAlias"),
        }
        status["mapper"] = await self._get_external_enduser_mapper_status(alias)
        status["default_role"] = await self._get_enduser_default_realm_role_status()
        return status

    async def _get_enduser_default_realm_role_status(self) -> dict[str, Any]:
        default_role_name = f"default-roles-{self.get_realm()}"
        composites = await self.get_realm_role_composites(default_role_name)
        return {
            "role": default_role_name,
            "includes_enduser": any(
                isinstance(role, dict) and role.get("name") == "enduser" for role in composites
            ),
        }

    async def _ensure_enduser_default_realm_role(self) -> dict[str, Any]:
        if not await self.get_realm_role("enduser"):
            await self.create_realm_role("enduser", "Standard end user access")

        default_role_name = f"default-roles-{self.get_realm()}"
        default_role = await self.get_realm_role(default_role_name)
        enduser_role = await self.get_realm_role("enduser")
        if not default_role or not enduser_role:
            return {
                "status": "skipped",
                "role": default_role_name,
                "reason": "default realm role or enduser role was not found",
            }

        composites = await self.get_realm_role_composites(default_role_name)
        if any(isinstance(role, dict) and role.get("name") == "enduser" for role in composites):
            return {"status": "exists", "role": default_role_name, "child_role": "enduser"}

        resp = await self._keycloak_request(
            "POST",
            f"/roles-by-id/{default_role['id']}/composites",
            json=[enduser_role],
        )
        if resp.status_code not in (200, 204):
            resp.raise_for_status()
        return {"status": "updated", "role": default_role_name, "child_role": "enduser"}

    async def _get_external_enduser_mapper_status(self, alias: str) -> dict[str, Any]:
        mapper_name = "assign-enduser-role"
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"exists": False, "name": mapper_name}
        resp.raise_for_status()
        mappers = resp.json()
        existing = next(
            (
                mapper
                for mapper in mappers
                if isinstance(mapper, dict) and mapper.get("name") == mapper_name
            ),
            None,
        )
        return {
            "exists": bool(existing),
            "name": mapper_name,
            "role": (existing or {}).get("config", {}).get("role"),
        }

    async def _ensure_external_enduser_mapper(self, alias: str) -> dict[str, Any]:
        mapper_name = "assign-enduser-role"
        payload = {
            "name": mapper_name,
            "identityProviderAlias": alias,
            "identityProviderMapper": "hardcoded-role-idp-mapper",
            "config": {"role": "enduser"},
        }
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"status": "skipped", "reason": "Identity provider not found"}
        resp.raise_for_status()
        mappers = resp.json()
        existing = next(
            (
                mapper
                for mapper in mappers
                if isinstance(mapper, dict) and mapper.get("name") == mapper_name
            ),
            None,
        )
        if existing and existing.get("id"):
            update_resp = await self._keycloak_request(
                "PUT",
                f"/identity-provider/instances/{quote(alias, safe='')}/mappers/{existing['id']}",
                json={**payload, "id": existing["id"]},
            )
            if update_resp.status_code not in (200, 204):
                update_resp.raise_for_status()
            return {"status": "updated", "name": mapper_name}

        create_resp = await self._keycloak_request(
            "POST",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
            json=payload,
        )
        if create_resp.status_code not in (200, 201, 204, 409):
            create_resp.raise_for_status()
        return {"status": "created", "name": mapper_name}

    async def _remove_external_enduser_mapper(self, alias: str) -> dict[str, Any]:
        mapper_name = "assign-enduser-role"
        mapper_types = {"hardcoded-role-idp-mapper", "oidc-hardcoded-role-idp-mapper"}
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"status": "skipped", "reason": "Identity provider not found"}
        resp.raise_for_status()
        mappers = resp.json()
        existing = next(
            (
                mapper
                for mapper in mappers
                if isinstance(mapper, dict)
                and (
                    mapper.get("name") == mapper_name
                    or (
                        mapper.get("identityProviderMapper") in mapper_types
                        and mapper.get("config", {}).get("role") == "enduser"
                    )
                )
            ),
            None,
        )
        if not existing or not existing.get("id"):
            return {"status": "absent", "name": mapper_name}

        delete_resp = await self._keycloak_request(
            "DELETE",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers/{existing['id']}",
        )
        if delete_resp.status_code not in (200, 204, 404):
            delete_resp.raise_for_status()
        return {"status": "deleted", "name": mapper_name}

    async def _ensure_external_groups_mappers(self, alias: str) -> dict[str, Any]:
        return {
            "identity_provider": await self._ensure_external_groups_claim_mapper(alias),
            "client": await self._ensure_login_client_groups_protocol_mapper(),
        }

    async def _ensure_external_groups_claim_mapper(self, alias: str) -> dict[str, Any]:
        mapper_name = "import-groups-claim"
        payload = {
            "name": mapper_name,
            "identityProviderAlias": alias,
            "identityProviderMapper": "oidc-user-attribute-idp-mapper",
            "config": {
                "claim": "groups",
                "user.attribute": "groups",
                "syncMode": "INHERIT",
            },
        }
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"status": "skipped", "reason": "Identity provider not found"}
        resp.raise_for_status()
        mappers = resp.json()
        existing = next(
            (
                mapper
                for mapper in mappers
                if isinstance(mapper, dict) and mapper.get("name") == mapper_name
            ),
            None,
        )
        if existing and existing.get("id"):
            update_resp = await self._keycloak_request(
                "PUT",
                f"/identity-provider/instances/{quote(alias, safe='')}/mappers/{existing['id']}",
                json={**payload, "id": existing["id"]},
            )
            if update_resp.status_code not in (200, 204):
                update_resp.raise_for_status()
            return {"status": "updated", "name": mapper_name}

        create_resp = await self._keycloak_request(
            "POST",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
            json=payload,
        )
        if create_resp.status_code not in (200, 201, 204, 409):
            create_resp.raise_for_status()
        return {"status": "created", "name": mapper_name}

    async def _ensure_login_client_groups_protocol_mapper(self) -> dict[str, Any]:
        client_id = self.get_login_client_id()
        client_uuid = await self.get_client_uuid(client_id=client_id)
        mapper_name = "groups"
        payload = {
            "name": mapper_name,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": "groups",
                "claim.name": "groups",
                "jsonType.label": "String",
                "multivalued": "true",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "userinfo.token.claim": "true",
            },
        }
        resp = await self._keycloak_request(
            "GET",
            f"/clients/{client_uuid}/protocol-mappers/models",
        )
        resp.raise_for_status()
        mappers = resp.json()
        existing = next(
            (
                mapper
                for mapper in mappers
                if isinstance(mapper, dict) and mapper.get("name") == mapper_name
            ),
            None,
        )
        if existing and existing.get("id"):
            update_resp = await self._keycloak_request(
                "PUT",
                f"/clients/{client_uuid}/protocol-mappers/models/{existing['id']}",
                json={**payload, "id": existing["id"]},
            )
            if update_resp.status_code not in (200, 204):
                update_resp.raise_for_status()
            return {"status": "updated", "name": mapper_name, "client_id": client_id}

        create_resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/protocol-mappers/models",
            json=payload,
        )
        if create_resp.status_code not in (200, 201, 204, 409):
            create_resp.raise_for_status()
        return {"status": "created", "name": mapper_name, "client_id": client_id}

    async def get_user_federated_identities(
        self,
        keycloak_id: str,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        resp = await self._keycloak_request(
            "GET",
            f"/users/{keycloak_id}/federated-identity",
            token=token,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        identities = resp.json()
        return identities if isinstance(identities, list) else []

    async def user_has_federated_identity(
        self,
        keycloak_id: str,
        alias: str | None = None,
    ) -> bool:
        identities = await self.get_user_federated_identities(keycloak_id)
        if not identities:
            return False
        if not alias:
            return True
        return any(
            isinstance(identity, dict) and identity.get("identityProvider") == alias
            for identity in identities
        )

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

    async def get_user_by_username(
        self, username: str, token: str | None = None
    ) -> dict[str, Any] | None:
        resp = await self._keycloak_request(
            "GET",
            f"/users?username={quote(username)}&exact=true",
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

    async def logout_user_sessions(self, keycloak_id: str) -> bool:
        """Terminate all active sessions for a Keycloak user."""
        resp = await self._keycloak_request("POST", f"/users/{keycloak_id}/logout")
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

    async def add_federated_identity(
        self,
        keycloak_id: str,
        external_user_id: str,
        external_username: str,
        alias: str | None = None,
    ) -> bool:
        provider_alias = alias or self.get_external_keycloak_alias()
        resp = await self._keycloak_request(
            "POST",
            f"/users/{keycloak_id}/federated-identity/{quote(provider_alias, safe='')}",
            json={
                "identityProvider": provider_alias,
                "userId": external_user_id,
                "userName": external_username,
            },
        )
        return resp.status_code in (200, 201, 204, 409)

    async def get_realm_role(
        self, role_name: str, token: str | None = None
    ) -> dict[str, Any] | None:
        resp = await self._keycloak_request("GET", f"/roles/{role_name}", token=token)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        role = resp.json()
        return role if isinstance(role, dict) else None

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

    async def delete_realm_role(self, role_name: str, token: str | None = None) -> bool:
        resp = await self._keycloak_request(
            "DELETE",
            f"/roles/{quote(role_name, safe='')}",
            token=token,
        )
        return resp.status_code in (200, 204, 404)

    async def get_realm_roles(self, token: str | None = None) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", "/roles", token=token)
        resp.raise_for_status()
        return resp.json()

    async def get_realm_role_composites(
        self,
        role_name: str,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        resp = await self._keycloak_request(
            "GET",
            f"/roles/{quote(role_name, safe='')}/composites",
            token=token,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        roles = resp.json()
        return roles if isinstance(roles, list) else []

    async def set_realm_role_composites(
        self,
        role_name: str,
        child_roles: list[dict[str, Any]],
        token: str | None = None,
    ) -> bool:
        role = await self.get_realm_role(role_name, token=token)
        if not role:
            return False

        role_id = role.get("id")
        if not role_id:
            return False

        existing = await self.get_realm_role_composites(role_name, token=token)
        if existing:
            remove_resp = await self._keycloak_request(
                "DELETE",
                f"/roles-by-id/{role_id}/composites",
                token=token,
                json=existing,
            )
            if remove_resp.status_code not in (200, 204):
                remove_resp.raise_for_status()

        desired_roles = []
        seen: set[tuple[str, str | None]] = set()
        for child in child_roles:
            child_name = child.get("name")
            child_client_id = child.get("clientId")
            key = (str(child_name), str(child_client_id) if child_client_id else None)
            if not child_name or child_name == role_name or key in seen:
                continue

            if child.get("clientRole"):
                child_role = await self.get_client_role(
                    str(child_name),
                    token=token,
                    client_id=str(child_client_id) if child_client_id else None,
                )
            else:
                child_role = await self.get_realm_role(str(child_name), token=token)

            if child_role:
                desired_roles.append(child_role)
                seen.add(key)

        if not desired_roles:
            return True

        add_resp = await self._keycloak_request(
            "POST",
            f"/roles-by-id/{role_id}/composites",
            token=token,
            json=desired_roles,
        )
        return add_resp.status_code in (200, 204)

    async def get_client_uuid(
        self,
        token: str | None = None,
        client_id: str | None = None,
    ) -> str:
        resolved_client_id = client_id or self.get_client_id()
        cache_key = f"{self.get_realm()}:{resolved_client_id}"
        if self._client_uuid_cache and self._client_uuid_cache_key == cache_key:
            return self._client_uuid_cache

        resp = await self._keycloak_request(
            "GET",
            f"/clients?clientId={quote(resolved_client_id)}",
            token=token,
        )
        resp.raise_for_status()
        clients = resp.json()
        if not isinstance(clients, list) or not clients:
            raise ValueError(t("keycloak.client_not_found", client_id=resolved_client_id))

        client = clients[0]
        if not isinstance(client, dict) or not client.get("id"):
            raise ValueError(t("keycloak.client_response_invalid", client_id=resolved_client_id))

        client_uuid = str(client["id"])
        self._client_uuid_cache = client_uuid
        self._client_uuid_cache_key = cache_key
        return client_uuid

    async def ensure_client(self, client_id: str, token: str | None = None) -> bool:
        try:
            await self.get_client_uuid(token=token, client_id=client_id)
            return False
        except ValueError:
            pass

        resp = await self._keycloak_request(
            "POST",
            "/clients",
            token=token,
            json={
                "clientId": client_id,
                "name": client_id,
                "protocol": "openid-connect",
                "enabled": True,
                "publicClient": False,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
            },
        )
        if resp.status_code not in (200, 201, 204, 409):
            resp.raise_for_status()

        if resp.status_code != 409:
            return True

        await self.get_client_uuid(token=token, client_id=client_id)
        return False

    async def get_client_role(
        self,
        role_name: str,
        token: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any] | None:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "GET",
            f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}",
            token=token,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        role = resp.json()
        return role if isinstance(role, dict) else None

    async def get_client_roles(
        self,
        token: str | None = None,
        client_id: str | None = None,
    ) -> list[dict[str, Any]]:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "GET",
            f"/clients/{client_uuid}/roles",
            token=token,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_client_role(
        self,
        role_name: str,
        description: str | None = None,
        token: str | None = None,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/roles",
            token=token,
            json={
                "name": role_name,
                "description": description or f"AgenticAI {role_name} client role",
            },
        )
        return resp.status_code in (200, 201, 204, 409)

    async def update_client_role(
        self,
        role_name: str,
        description: str | None = None,
        token: str | None = None,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        role = await self.get_client_role(role_name, token=token, client_id=client_id)
        if not role:
            return False
        role["description"] = description or role.get("description") or ""
        resp = await self._keycloak_request(
            "PUT",
            f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}",
            token=token,
            json=role,
        )
        return resp.status_code in (200, 204)

    async def delete_client_role(
        self,
        role_name: str,
        token: str | None = None,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "DELETE",
            f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}",
            token=token,
        )
        return resp.status_code in (200, 204, 404)

    async def get_client_role_composites(
        self,
        role_name: str,
        token: str | None = None,
        client_id: str | None = None,
    ) -> list[dict[str, Any]]:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        role = await self.get_client_role(role_name, token=token, client_id=client_id)
        if not role:
            return []

        resp = await self._keycloak_request(
            "GET",
            f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}/composites/clients/{client_uuid}",
            token=token,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    async def set_role_composites(
        self,
        role_name: str,
        child_roles: list[dict[str, Any]],
        token: str | None = None,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        role = await self.get_client_role(role_name, token=token, client_id=client_id)
        if not role:
            return False

        existing = await self.get_client_role_composites(
            role_name,
            token=token,
            client_id=client_id,
        )
        if existing:
            remove_resp = await self._keycloak_request(
                "DELETE",
                f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}/composites",
                token=token,
                json=existing,
            )
            if remove_resp.status_code not in (200, 204):
                remove_resp.raise_for_status()

        desired_roles = []
        seen: set[str] = set()
        for child in child_roles:
            child_name = child.get("name")
            if not child_name or child_name == role_name or child_name in seen:
                continue
            child_role = await self.get_client_role(
                str(child_name),
                token=token,
                client_id=client_id,
            )
            if child_role:
                desired_roles.append(child_role)
                seen.add(str(child_name))

        if not desired_roles:
            return True

        add_resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/roles/{quote(role_name, safe='')}/composites",
            token=token,
            json=desired_roles,
        )
        return add_resp.status_code in (200, 204)

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
        if current_roles_resp.status_code == 404:
            current_roles = []
        else:
            current_roles_resp.raise_for_status()
            current_roles_payload = current_roles_resp.json()
            current_roles = current_roles_payload if isinstance(current_roles_payload, list) else []

        roles_to_remove = [
            r for r in current_roles if isinstance(r, dict) and r.get("name") != role_name
        ]

        if roles_to_remove:
            await self._keycloak_request(
                "DELETE", f"/users/{keycloak_id}/role-mappings/realm", json=roles_to_remove
            )

        await self._keycloak_request(
            "POST", f"/users/{keycloak_id}/role-mappings/realm", json=[role]
        )
        return True

    async def assign_client_role(
        self,
        keycloak_id: str,
        role_name: str,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(client_id=client_id)
        role = await self.get_client_role(role_name, client_id=client_id)
        if not role:
            await self.create_client_role(role_name, client_id=client_id)
            role = await self.get_client_role(role_name, client_id=client_id)
            if not role:
                return False

        resp = await self._keycloak_request(
            "POST",
            f"/users/{keycloak_id}/role-mappings/clients/{client_uuid}",
            json=[role],
        )
        return resp.status_code in (200, 204)

    async def remove_client_role(
        self,
        keycloak_id: str,
        role_name: str,
        client_id: str | None = None,
    ) -> bool:
        client_uuid = await self.get_client_uuid(client_id=client_id)
        role = await self.get_client_role(role_name, client_id=client_id)
        if not role:
            return True

        resp = await self._keycloak_request(
            "DELETE",
            f"/users/{keycloak_id}/role-mappings/clients/{client_uuid}",
            json=[role],
        )
        return resp.status_code in (200, 204)

    async def get_user_client_roles(
        self,
        keycloak_id: str,
        token: str | None = None,
        client_id: str | None = None,
    ) -> list[dict[str, Any]]:
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "GET",
            f"/users/{keycloak_id}/role-mappings/clients/{client_uuid}",
            token=token,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        roles = resp.json()
        return roles if isinstance(roles, list) else []

    async def set_client_role(
        self,
        keycloak_id: str,
        role_name: str,
        client_id: str | None = None,
    ) -> bool:
        current_roles = await self.get_user_client_roles(keycloak_id, client_id=client_id)
        roles_to_remove = [r for r in current_roles if r.get("name") != role_name]
        for role in roles_to_remove:
            name = role.get("name")
            if name:
                await self.remove_client_role(keycloak_id, str(name), client_id=client_id)
        return await self.assign_client_role(keycloak_id, role_name, client_id=client_id)

    async def clear_user_client_roles(
        self,
        keycloak_id: str,
        client_id: str | None = None,
    ) -> bool:
        current_roles = await self.get_user_client_roles(keycloak_id, client_id=client_id)
        for role in current_roles:
            name = role.get("name")
            if name:
                await self.remove_client_role(keycloak_id, str(name), client_id=client_id)
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

    def _login_client_credentials_payload(self) -> dict[str, str]:
        payload = {"client_id": self.get_login_client_id()}
        return payload

    async def get_oidc_authorize_url(
        self,
        redirect_uri: str,
        state: str | None = None,
        idp_hint: str | None = None,
        prompt: str | None = None,
    ) -> str:
        client_id = self.get_login_client_id()
        base_url = self.get_base_url()
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
        }
        if state:
            params["state"] = state
        if idp_hint:
            params["kc_idp_hint"] = idp_hint
        if prompt:
            params["prompt"] = prompt
        import urllib.parse

        query = urllib.parse.urlencode(params)
        return f"{base_url}/realms/{self.get_realm()}/protocol/openid-connect/auth?{query}"

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
                    **self._login_client_credentials_payload(),
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
                return t("keycloak.token_exchange_failed_status", status=response.status_code)

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

        Uses the login client (agenticai-web, public) rather than the backend service client,
        because public clients have directAccessGrantsEnabled=true.

        Returns Keycloak token payload { access_token, refresh_token, id_token, expires_in, token_type }.
        Raises ValueError on authentication failure.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": self.get_login_client_id(),
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
                    # Keycloak can return error="invalid_grant" for several distinct
                    # reasons -- a genuinely wrong username/password, but also a
                    # disabled account or, in some Keycloak versions, a misconfigured
                    # login client not permitted for direct access grants. Only the
                    # description Keycloak actually uses for wrong credentials is
                    # translated; every other case (including other invalid_grant
                    # causes) is left as Keycloak's raw description so a real
                    # deployment/config problem isn't mislabeled as a user typo.
                    description = (error_body.get("error_description") or "").lower()
                    if error_body.get("error") == "invalid_grant" and "credential" in description:
                        detail = t("auth.invalid_credentials")
                    else:
                        detail = (
                            error_body.get("error_description")
                            or error_body.get("error")
                            or t("keycloak.auth_failed_status", status=resp.status_code)
                        )
            except Exception:
                detail = t("keycloak.auth_failed_status", status=resp.status_code)
            raise ValueError(detail)

    async def get_external_user_info(self, access_token: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.get_external_issuer_url()}/protocol/openid-connect/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            return resp.json()

    async def ensure_sp_user_for_external_identity(
        self,
        *,
        external_subject: str,
        username: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        """Mirror an external IdP user into the SP realm and assign enduser."""
        user = await self.get_user_by_username(username)
        if not user and email:
            user = await self.get_user_by_email(email)

        payload: dict[str, Any] = {
            "username": username,
            "email": email,
            "enabled": True,
            "emailVerified": True,
            "attributes": {
                "external_keycloak_sub": [external_subject],
                "external_keycloak_alias": [self.get_external_keycloak_alias()],
            },
        }
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name

        if user and user.get("id"):
            await self.update_user(str(user["id"]), {**user, **payload})
            keycloak_id = str(user["id"])
        else:
            created_id = await self.create_user(payload)
            if not created_id:
                user = await self.get_user_by_username(username)
                created_id = str(user["id"]) if user and user.get("id") else None
            if not created_id:
                raise ValueError(t("keycloak.sp_user_create_failed"))
            keycloak_id = created_id

        await self.add_federated_identity(
            keycloak_id,
            external_user_id=external_subject,
            external_username=username,
        )
        await self.set_realm_role(keycloak_id, "enduser")
        profile = await self.get_user_profile(keycloak_id)
        return profile or {"id": keycloak_id, **payload}

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
                    **self._login_client_credentials_payload(),
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
                        or t("keycloak.token_refresh_failed_status", status=resp.status_code)
                    )
            except Exception:
                detail = t("keycloak.token_refresh_failed_status", status=resp.status_code)
            raise ValueError(detail)

    # ------------------------------------------------------------------
    # Protocol mapper management — used to add permissions claim to JWT
    # ------------------------------------------------------------------

    async def get_protocol_mappers(
        self,
        client_id: str,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all protocol mappers on a client."""
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "GET",
            f"/clients/{client_uuid}/protocol-mappers/models",
            token=token,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    async def create_protocol_mapper(
        self,
        client_id: str,
        mapper_config: dict[str, Any],
        token: str | None = None,
    ) -> bool:
        """Create a protocol mapper on a client.

        Example mapper_config for client-role mapper::

            {
                "name": "permissions-agent-service",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-client-role-mapper",
                "config": {
                    "access.token.claim": "true",
                    "claim.name": "permissions",
                    "id.token.claim": "true",
                    "multivalued": "true",
                    "aggregate.attrs": "true",
                    "usermodel.clientRoleMapping.clientId": "agent-service",
                    "userinfo.token.claim": "true"
                }
            }
        """
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/protocol-mappers/models",
            token=token,
            json=mapper_config,
        )
        return resp.status_code in (200, 201, 204, 409)

    async def delete_protocol_mapper(
        self,
        client_id: str,
        mapper_id: str,
        token: str | None = None,
    ) -> bool:
        """Delete a protocol mapper from a client by its ID."""
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "DELETE",
            f"/clients/{client_uuid}/protocol-mappers/models/{mapper_id}",
            token=token,
        )
        return resp.status_code in (200, 204, 404)

    async def ensure_permissions_protocol_mappers(
        self,
        backend_clients: list[str] | None = None,
        token: str | None = None,
    ) -> dict[str, bool]:
        """Ensure protocol mappers exist on the frontend client (agenticai-web)
        for all backend service clients. Each mapper maps client roles from the
        backend client into the ``permissions`` JWT claim.

        Returns a dict mapping mapper name -> created/existed status.
        """
        frontend_client_id = self.get_login_client_id()
        results: dict[str, bool] = {}

        if backend_clients is None:
            backend_clients = [
                "user-service",
                "agent-service",
                "rag-service",
                "tools-service",
            ]

        existing_mappers = await self.get_protocol_mappers(frontend_client_id, token=token)
        existing_names = {m.get("name") for m in existing_mappers if isinstance(m, dict)}

        for svc_client in backend_clients:
            mapper_name = f"permissions-{svc_client}"
            if mapper_name in existing_names:
                results[mapper_name] = True
                continue

            created = await self.create_protocol_mapper(
                frontend_client_id,
                {
                    "name": mapper_name,
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-usermodel-client-role-mapper",
                    "config": {
                        "access.token.claim": "true",
                        "claim.name": "permissions",
                        "id.token.claim": "true",
                        "multivalued": "true",
                        "aggregate.attrs": "true",
                        "usermodel.clientRoleMapping.clientId": svc_client,
                        "userinfo.token.claim": "true",
                    },
                },
                token=token,
            )
            results[mapper_name] = created

        return results

    async def remove_permissions_protocol_mappers(
        self,
        token: str | None = None,
    ) -> dict[str, bool]:
        """Remove all permissions-* protocol mappers from the frontend client.

        These mappers were putting fine-grained permissions into the JWT.
        Now coarse roles appear via Keycloak's default resource_access.
        """
        frontend_client_id = self.get_login_client_id()
        results: dict[str, bool] = {}

        existing_mappers = await self.get_protocol_mappers(frontend_client_id, token=token)
        for mapper in existing_mappers:
            name = mapper.get("name", "")
            mapper_id = mapper.get("id", "")
            if name.startswith("permissions-"):
                deleted = await self.delete_protocol_mapper(
                    frontend_client_id, mapper_id, token=token
                )
                results[name] = deleted

        return results

    # ------------------------------------------------------------------
    # Client secret management
    # ------------------------------------------------------------------

    async def generate_client_secret(
        self,
        client_id: str,
        token: str | None = None,
    ) -> str | None:
        """Generate a new client secret for a confidential client.

        Returns the new secret value, or None on failure.
        """
        client_uuid = await self.get_client_uuid(token=token, client_id=client_id)
        resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/client-secret",
            token=token,
        )
        if resp.status_code not in (200, 204):
            return None
        data = resp.json()
        return str(data.get("value", "")) if isinstance(data, dict) else None

    # ------------------------------------------------------------------
    # Backchannel logout
    # ------------------------------------------------------------------

    async def backchannel_logout(
        self, refresh_token: str | None = None, id_token_hint: str | None = None
    ) -> bool:
        async with httpx.AsyncClient() as client:
            data = {}
            if refresh_token:
                data["refresh_token"] = refresh_token
            if id_token_hint:
                data["id_token_hint"] = id_token_hint
            credentials = (
                self._login_client_credentials_payload()
                if refresh_token or id_token_hint
                else self._client_credentials_payload()
            )
            resp = await client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/logout",
                data={**data, **credentials},
            )
            return resp.status_code in (200, 204, 400)


_keycloak_service = KeycloakService()


def get_keycloak_service() -> KeycloakService:
    return _keycloak_service
