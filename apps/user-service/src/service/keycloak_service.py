from collections.abc import Awaitable
from contextlib import asynccontextmanager
from contextvars import ContextVar
import math
import time
from typing import Any, ClassVar
from urllib.parse import quote, urlparse

from cachetools import LRUCache
from config_manager import env
from error_contract import (
    BadRequestError,
    ConfigurationError,
    ConflictError,
    DependencyAuthenticationError,
    DependencyRateLimitedError,
    DependencyResponseError,
    NotFoundError,
    UnauthorizedError,
    from_httpx_error,
    raise_for_httpx_response,
    render_error_message,
)
import httpx
from security import get_shared_client, reveal_secret

from src.service import keycloak_helpers
from src.service.keycloak_broker import KeycloakBrokerMixin

_settings = env

_ADMIN_REQUEST_CLIENT: ContextVar[tuple[object, httpx.AsyncClient] | None] = ContextVar(
    "keycloak_admin_request_client", default=None
)

# httpx applies its 5s default to every phase, including reading the body. A
# Keycloak admin page over a large directory routinely takes longer than that,
# so the read budget is set per workload instead of left at the default.
_HTTP_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=30.0)
# Interactive calls: permission writes, token exchange, single-user reads.
_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=15.0)
# Bulk directory walks: role membership and group member enumeration.
DIRECTORY_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=15.0, pool=30.0)


def new_http_client(timeout: httpx.Timeout | None = None) -> httpx.AsyncClient:
    """An httpx client with timeouts that suit Keycloak rather than the defaults."""
    return httpx.AsyncClient(timeout=timeout or _HTTP_TIMEOUT, limits=_HTTP_LIMITS)


async def _keycloak_http(request: Awaitable[httpx.Response]) -> httpx.Response:
    try:
        return await request
    except httpx.HTTPError as exc:
        raise from_httpx_error(exc) from exc


def _keycloak_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise DependencyResponseError() from exc


def _raise_dependency_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise DependencyRateLimitedError()
    if response.status_code in {401, 403}:
        raise DependencyAuthenticationError()
    raise DependencyResponseError()


def _raise_keycloak_status(response: httpx.Response) -> None:
    """Translate unhandled remote statuses after operation-specific decisions."""
    if response.status_code < 400:
        return
    if response.status_code == 404:
        raise NotFoundError()
    if response.status_code == 409:
        raise ConflictError()
    if response.status_code in {400, 422}:
        raise BadRequestError()
    _raise_dependency_status(response)


def _classify_admin_status(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise DependencyRateLimitedError()
    if response.status_code in {401, 403}:
        raise DependencyAuthenticationError()
    if response.status_code >= 500:
        raise DependencyResponseError()


def _unwrap_secret(value):
    """Extract plain text from a ``SecretStr``, or return the value as-is."""
    return reveal_secret(value)


class KeycloakService(KeycloakBrokerMixin):
    _runtime_settings: ClassVar[dict[str, Any]] = {}
    _runtime_generation: int = 0
    # Bounded and keyed: a single cache slot meant that fetching one admin
    # token (e.g. "service-account") silently evicted a different, still
    # valid one ("password-admin") cached moments earlier. Expiry stays a
    # manual (token, expires_at) check since it tracks each token's own
    # server-issued lifetime, not a fixed TTL.
    _admin_token_cache: ClassVar[LRUCache[str, tuple[str, float]]] = LRUCache(maxsize=8)
    _client_uuid_cache: ClassVar[LRUCache[str, str]] = LRUCache(maxsize=8)

    @classmethod
    def set_runtime_settings(cls, settings: dict[str, Any]) -> None:
        cls._runtime_generation += 1
        cls._runtime_settings = {key: value for key, value in settings.items() if value is not None and value != ""}
        cls._admin_token_cache.clear()
        cls._client_uuid_cache.clear()

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
    def _str_config(cls, key: str, fallback=None) -> str | None:
        value = cls._runtime_value(key)
        if value is None:
            resolved = _unwrap_secret(fallback)
            return str(resolved) if resolved is not None else None
        resolved_value = _unwrap_secret(value) or value
        text = str(resolved_value).strip()
        if text:
            return text
        resolved_fb = _unwrap_secret(fallback)
        return str(resolved_fb) if resolved_fb is not None else None

    @classmethod
    def _env_bool_config(cls, key: str) -> bool | None:
        value = getattr(_settings, key, None)
        if value is None:
            return None
        return str(value).lower() == "true"

    @classmethod
    def _env_str_config(cls, key: str) -> str | None:
        value = _unwrap_secret(getattr(_settings, key, None))
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

    @staticmethod
    def has_admin_access() -> bool:
        """Whether the Keycloak admin REST API is accessible.

        This is a capability hint only. Internal Keycloak exposes the
        admin REST API through the configured client's service account.
        """
        return KeycloakService()._admin_credentials_configured() or bool(KeycloakService().get_client_secret())

    def get_base_url(self) -> str:
        base_url = self._str_config(
            "KEYCLOAK_BASE_URL",
            _settings.KEYCLOAK_BASE_URL,
        )
        if base_url:
            return base_url.rstrip("/")

        issuer_url = self._str_config(
            "KEYCLOAK_ISSUER_URL",
            _settings.KEYCLOAK_ISSUER_URL,
        )
        if issuer_url:
            return issuer_url.rstrip("/").replace(f"/realms/{self.get_realm()}", "")

        raise ConfigurationError(message_key="errors.user_service.keycloak.base_url_not_configured", message_params={})

    def get_realm(self) -> str:
        return (
            self._str_config("KEYCLOAK_REALM", _settings.KEYCLOAK_REALM)
            or _settings.KEYCLOAK_REALM
        )

    def get_client_id(self) -> str:
        return self._str_config(
            "KEYCLOAK_USER_SERVICE_CLIENT_ID",
            _settings.KEYCLOAK_USER_SERVICE_CLIENT_ID,
        ) or _settings.KEYCLOAK_USER_SERVICE_CLIENT_ID

    def get_login_client_id(self) -> str:
        """Client ID used for Direct Access Grant (password) login.
        Uses a separate public client (web-client) that has directAccessGrantsEnabled=true."""
        return self._str_config(
            "KEYCLOAK_LOGIN_CLIENT_ID",
            _settings.KEYCLOAK_LOGIN_CLIENT_ID,
        ) or _settings.KEYCLOAK_LOGIN_CLIENT_ID

    def get_client_secret(self) -> str | None:
        secret = self._str_config(
            "KEYCLOAK_USER_SERVICE_CLIENT_SECRET",
            _settings.KEYCLOAK_USER_SERVICE_CLIENT_SECRET,
        )
        return secret.strip() if secret and secret.strip() else None

    def get_oidc_redirect_uri(self) -> str:
        redirect_uri = self._str_config(
            "KEYCLOAK_REDIRECT_URI",
            _settings.KEYCLOAK_REDIRECT_URI,
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

        raise BadRequestError(message_key="errors.user_service.keycloak.redirect_uri_not_absolute", message_params={})

    def is_external_keycloak(self) -> bool:
        return self._external_bool_config(
            "EXTERNAL_KEYCLOAK",
            _settings.EXTERNAL_KEYCLOAK,
        )

    def _client_credentials_payload(self) -> dict[str, str]:
        payload = {"client_id": self.get_client_id()}
        client_secret = self.get_client_secret()
        if client_secret:
            payload["client_secret"] = client_secret
        return payload

    def _admin_credentials_configured(self) -> bool:
        username_configured = bool(self._str_config("KEYCLOAK_ADMIN", _settings.KEYCLOAK_ADMIN))
        password_configured = bool(self._str_config("KEYCLOAK_ADMIN_PASSWORD", _settings.KEYCLOAK_ADMIN_PASSWORD))
        return username_configured and password_configured

    def get_issuer_url(self) -> str | None:
        issuer = self._str_config(
            "KEYCLOAK_ISSUER_URL",
            _settings.KEYCLOAK_ISSUER_URL,
        )
        return issuer.rstrip("/") if issuer else None

    async def _get_cached_admin_token(self, cache_key: str) -> str | None:
        cached = self._admin_token_cache.get(cache_key)
        if cached and time.time() < cached[1]:
            return cached[0]
        return None

    def _cache_admin_token(self, cache_key: str, token_data: dict[str, Any]) -> str:
        if not token_data.get("access_token"):
            raise DependencyResponseError()
        token = str(token_data["access_token"])
        try:
            lifetime = float(token_data.get("expires_in", 300))
        except (TypeError, ValueError):
            lifetime = 0
        if not math.isfinite(lifetime) or lifetime <= 0:
            lifetime = 0
        refresh_at = time.time() + lifetime - min(60, lifetime * 0.1)
        self._admin_token_cache[cache_key] = (token, refresh_at)
        return token

    async def _get_password_admin_token(self) -> str:
        cached = await self._get_cached_admin_token("password-admin")
        if cached:
            return cached
        admin_realm = "master"
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        resp = await _keycloak_http(
            client.post(
                f"{self.get_base_url()}/realms/{admin_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "username": self._str_config(
                        "KEYCLOAK_ADMIN",
                        _settings.KEYCLOAK_ADMIN,
                    ),
                    "password": self._str_config(
                        "KEYCLOAK_ADMIN_PASSWORD",
                        _settings.KEYCLOAK_ADMIN_PASSWORD,
                    ),
                    "client_id": "admin-cli",
                },
            )
        )
        raise_for_httpx_response(resp)
        return self._cache_admin_token("password-admin", resp.json())

    async def _get_service_account_admin_token(self) -> str:
        if not self.get_client_secret():
            raise ConfigurationError(
                message_key="errors.user_service.keycloak.service_account_not_configured",
                message_params={},
            )
        cached = await self._get_cached_admin_token("service-account")
        if cached:
            return cached
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        resp = await _keycloak_http(
            client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    **self._client_credentials_payload(),
                },
            )
        )
        raise_for_httpx_response(resp)
        return self._cache_admin_token("service-account", resp.json())

    async def _get_admin_token(self) -> str:
        if self._admin_credentials_configured():
            return await self._get_password_admin_token()
        return await self._get_service_account_admin_token()

    @asynccontextmanager
    async def admin_request_scope(self, client_timeout: httpx.Timeout | None = None):
        """Reuse connections within one awaited operation, including its child tasks."""
        current = _ADMIN_REQUEST_CLIENT.get()
        if current is not None and current[0] is self and not current[1].is_closed:
            yield
            return
        async with new_http_client(client_timeout) as client:
            token = _ADMIN_REQUEST_CLIENT.set((self, client))
            try:
                yield
            finally:
                _ADMIN_REQUEST_CLIENT.reset(token)

    async def _keycloak_request(self, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token or await self._get_admin_token()}"
        url = f"{self.get_base_url()}/admin/realms/{self.get_realm()}{path}"
        current = _ADMIN_REQUEST_CLIENT.get()
        if current is not None and current[0] is self and not current[1].is_closed:
            return await current[1].request(method, url, headers=headers, **kwargs)

        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        url = f"{self.get_base_url()}/admin/realms/{self.get_realm()}{path}"
        resp = await _keycloak_http(client.request(method, url, headers=headers, **kwargs))
        _classify_admin_status(resp)
        return resp

    async def get_realm_configuration(self) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", "")
        _raise_keycloak_status(resp)
        return _keycloak_json(resp)

    async def update_realm_configuration(self, updates: dict[str, Any]) -> dict[str, Any]:
        realm_config = await self.get_realm_configuration()
        payload = {**realm_config, **updates}
        resp = await self._keycloak_request("PUT", "", json=payload)
        if resp.status_code not in (200, 204):
            _raise_keycloak_status(resp)
        return await self.get_realm_configuration()

    async def get_user_profile(self, keycloak_id: str, token: str | None = None) -> dict[str, Any]:
        resp = await self._keycloak_request("GET", f"/users/{keycloak_id}", token=token)
        if resp.status_code == 404:
            return {}
        _raise_keycloak_status(resp)
        return _keycloak_json(resp)

    def get_external_keycloak_alias(self) -> str:
        alias = self._external_str_config(
            "EXTERNAL_KEYCLOAK_ALIAS",
            _settings.EXTERNAL_KEYCLOAK_ALIAS,
        )
        return alias.strip() or "external-keycloak"

    def _external_issuer_url(self) -> str:
        issuer = self._external_str_config(
            "EXTERNAL_KEYCLOAK_ISSUER_URL",
            _settings.EXTERNAL_KEYCLOAK_ISSUER_URL,
        )
        if issuer:
            return issuer.rstrip("/")

        base_url = self._external_str_config(
            "EXTERNAL_KEYCLOAK_BASE_URL",
            _settings.EXTERNAL_KEYCLOAK_BASE_URL,
        )
        realm = self._external_str_config(
            "EXTERNAL_KEYCLOAK_REALM",
            _settings.EXTERNAL_KEYCLOAK_REALM,
        )
        if not base_url or not realm:
            raise ConfigurationError(
                message_key="errors.user_service.keycloak.external_issuer_not_configured",
                message_params={},
            )
        return f"{base_url.rstrip('/')}/realms/{realm}"

    def get_external_issuer_url(self) -> str:
        return self._external_issuer_url()

    def _external_backend_issuer_url(self) -> str:
        issuer = self._external_str_config(
            "EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL",
            _settings.EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL,
        )
        return issuer.rstrip("/") if issuer else self._external_issuer_url()

    def get_external_broker_redirect_uri(self) -> str:
        return f"{self.get_base_url()}/realms/{self.get_realm()}/broker/{self.get_external_keycloak_alias()}/endpoint"

    def _external_admin_credentials_configured(self) -> bool:
        return bool(
            self._external_str_config(
                "EXTERNAL_KEYCLOAK_ADMIN",
                _settings.EXTERNAL_KEYCLOAK_ADMIN,
            )
            and self._external_str_config(
                "EXTERNAL_KEYCLOAK_ADMIN_PASSWORD",
                _settings.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD,
            )
        )

    async def _get_external_admin_token(self) -> str:
        cached = await self._get_cached_admin_token("external-password-admin")
        if cached:
            return cached

        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        resp = await client.post(
            f"{self._external_backend_issuer_url().rsplit('/realms/', 1)[0]}"
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "username": self._external_str_config(
                    "EXTERNAL_KEYCLOAK_ADMIN",
                    _settings.EXTERNAL_KEYCLOAK_ADMIN,
                ),
                "password": self._external_str_config(
                    "EXTERNAL_KEYCLOAK_ADMIN_PASSWORD",
                    _settings.EXTERNAL_KEYCLOAK_ADMIN_PASSWORD,
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
            _settings.EXTERNAL_KEYCLOAK_REALM,
        )
        if not external_realm:
            raise ConfigurationError(
                message_key="errors.user_service.keycloak.external_realm_not_configured",
                message_params={},
            )

        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        base_url = self._external_backend_issuer_url().rsplit("/realms/", 1)[0]
        response = await _keycloak_http(
            client.request(
                method,
                f"{base_url}/admin/realms/{external_realm}{path}",
                headers=headers,
                **kwargs,
            )
        )
        _classify_admin_status(response)
        return response

    def _external_idp_payload(self) -> dict[str, Any]:
        client_id = self._external_str_config(
            "EXTERNAL_KEYCLOAK_CLIENT_ID",
            _settings.EXTERNAL_KEYCLOAK_CLIENT_ID,
        )
        client_secret = self._external_str_config(
            "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
            _settings.EXTERNAL_KEYCLOAK_CLIENT_SECRET,
        )
        if not client_id:
            raise ConfigurationError(
                message_key="errors.user_service.keycloak.external_client_id_not_configured",
                message_params={},
            )
        if not client_secret:
            raise ConfigurationError(
                message_key="errors.user_service.keycloak.external_client_secret_not_configured",
                message_params={},
            )

        alias = self.get_external_keycloak_alias()
        issuer = self._external_issuer_url()
        backend_issuer = self._external_backend_issuer_url()
        display_name = (
            self._external_str_config(
                "EXTERNAL_KEYCLOAK_DISPLAY_NAME",
                _settings.EXTERNAL_KEYCLOAK_DISPLAY_NAME,
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

    def _login_client_redirect_uris(self) -> list[str]:
        raw = self._str_config(
            "KEYCLOAK_REDIRECT_URIS",
            _settings.KEYCLOAK_REDIRECT_URIS or _settings.KEYCLOAK_REDIRECT_URI,
        )
        return keycloak_helpers.csv_values(raw) or ["*"]

    def _login_client_web_origins(self) -> list[str]:
        raw = self._str_config(
            "KEYCLOAK_WEB_ORIGINS",
            _settings.KEYCLOAK_WEB_ORIGINS,
        )
        return keycloak_helpers.csv_values(raw) or ["+"]

    def _login_client_post_logout_redirect_uris(self) -> str:
        return (
            self._str_config(
                "KEYCLOAK_POST_LOGOUT_REDIRECT_URIS",
                _settings.KEYCLOAK_POST_LOGOUT_REDIRECT_URIS,
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
            _raise_keycloak_status(resp)
            current = _keycloak_json(resp)
            if not isinstance(current, dict):
                raise DependencyResponseError(
                    message_key="errors.user_service.keycloak.client_response_invalid",
                    message_params={"client_id": client_id},
                )
            action = "updated"
        except NotFoundError:
            current = {
                "clientId": client_id,
                "name": client_id,
                "protocol": "openid-connect",
                "attributes": {},
            }
            action = "created"

        attributes = dict(current.get("attributes") or {})
        attributes["post.logout.redirect.uris"] = keycloak_helpers.merge_post_logout_redirect_uris(
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
            "redirectUris": keycloak_helpers.merge_unique_values(
                list(current.get("redirectUris") or []),
                self._login_client_redirect_uris(),
            ),
            "webOrigins": keycloak_helpers.merge_unique_values(
                list(current.get("webOrigins") or []),
                self._login_client_web_origins(),
            ),
            "attributes": attributes,
        }
        payload.pop("secret", None)

        if action == "created":
            create_resp = await self._keycloak_request("POST", "/clients", json=payload)
            if create_resp.status_code not in (200, 201, 204, 409):
                _raise_keycloak_status(create_resp)
            if create_resp.status_code == 409:
                action = "updated"
                client_uuid = await self.get_client_uuid(client_id=client_id)
                update_resp = await self._keycloak_request(
                    "PUT",
                    f"/clients/{client_uuid}",
                    json=payload,
                )
                if update_resp.status_code not in (200, 204):
                    _raise_keycloak_status(update_resp)
            else:
                self._client_uuid_cache.pop(f"{self.get_realm()}:{client_id}", None)
        else:
            update_resp = await self._keycloak_request(
                "PUT",
                f"/clients/{client_uuid}",
                json=payload,
            )
            if update_resp.status_code not in (200, 204):
                _raise_keycloak_status(update_resp)

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

        web_origin = keycloak_helpers.origin_from_url(redirect_uri)
        if web_origin is None:
            return {
                "status": "skipped",
                "reason": "redirect_uri is not an absolute HTTP(S) URL",
                "redirect_uri": redirect_uri,
            }

        client_id = self.get_login_client_id()
        client_uuid = await self.get_client_uuid(client_id=client_id)
        resp = await self._keycloak_request("GET", f"/clients/{client_uuid}")
        _raise_keycloak_status(resp)
        current = _keycloak_json(resp)
        if not isinstance(current, dict):
            raise DependencyResponseError(
                message_key="errors.user_service.keycloak.client_response_invalid",
                message_params={"client_id": client_id},
            )

        current_redirect_uris = keycloak_helpers.merge_unique_values(list(current.get("redirectUris") or []), [])
        current_web_origins = keycloak_helpers.merge_unique_values(list(current.get("webOrigins") or []), [])
        attributes = dict(current.get("attributes") or {})
        current_post_logout_redirect_uris = keycloak_helpers.post_logout_redirect_values(
            attributes.get("post.logout.redirect.uris")
        )
        redirect_exists = keycloak_helpers.value_matches_pattern(redirect_uri, current_redirect_uris)
        origin_exists = keycloak_helpers.value_matches_pattern(web_origin, current_web_origins)
        post_logout_exists = (
            not post_logout_redirect_uri
            or post_logout_redirect_uri in current_post_logout_redirect_uris
            or keycloak_helpers.value_matches_pattern(
                post_logout_redirect_uri,
                [uri for uri in current_post_logout_redirect_uris if uri != "+"],
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
            "redirectUris": current_redirect_uris if redirect_exists else [*current_redirect_uris, redirect_uri],
            "webOrigins": current_web_origins if origin_exists else [*current_web_origins, web_origin],
            "attributes": attributes,
        }
        payload.pop("secret", None)
        update_resp = await self._keycloak_request("PUT", f"/clients/{client_uuid}", json=payload)
        if update_resp.status_code not in (200, 204):
            _raise_keycloak_status(update_resp)

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
        existing_resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}",
        )
        if existing_resp.status_code == 404:
            payload = self._external_idp_payload()
            resp = await self._keycloak_request(
                "POST",
                "/identity-provider/instances",
                json=payload,
            )
            if resp.status_code not in (200, 201, 204, 409):
                _raise_keycloak_status(resp)
            action = "created"
            sync_result: dict[str, str] = {"status": action}
        else:
            _raise_keycloak_status(existing_resp)
            try:
                payload = self._external_idp_payload()
            except ConfigurationError as exc:
                action = "exists"
                sync_result = {"status": "skipped", "reason": render_error_message(exc)}
            else:
                resp = await self._keycloak_request(
                    "PUT",
                    f"/identity-provider/instances/{quote(alias, safe='')}",
                    json=payload,
                )
                if resp.status_code not in (200, 204):
                    _raise_keycloak_status(resp)
                action = "updated"
                sync_result = {"status": action}

        default_role_result = await self._ensure_enduser_default_realm_role()
        mapper_result = await self._remove_external_enduser_mapper(alias)
        groups_mapper_result = await self._ensure_external_groups_mappers(alias)
        external_client_result = await self.ensure_external_client_redirect_uri()
        return {
            "status": action,
            "alias": alias,
            "sync": sync_result,
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
            _settings.EXTERNAL_KEYCLOAK_CLIENT_ID,
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
        _raise_keycloak_status(resp)
        clients = _keycloak_json(resp)
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
        _raise_keycloak_status(client_resp)
        payload = _keycloak_json(client_resp)
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
            _raise_keycloak_status(update_resp)

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
        _raise_keycloak_status(resp)

        provider = _keycloak_json(resp)
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
            "includes_enduser": any(isinstance(role, dict) and role.get("name") == "enduser" for role in composites),
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
            _raise_keycloak_status(resp)
        return {"status": "updated", "role": default_role_name, "child_role": "enduser"}

    async def _get_external_enduser_mapper_status(self, alias: str) -> dict[str, Any]:
        mapper_name = "assign-enduser-role"
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"exists": False, "name": mapper_name}
        _raise_keycloak_status(resp)
        mappers = _keycloak_json(resp)
        existing = next(
            (mapper for mapper in mappers if isinstance(mapper, dict) and mapper.get("name") == mapper_name),
            None,
        )
        return {
            "exists": bool(existing),
            "name": mapper_name,
            "role": (existing or {}).get("config", {}).get("role"),
        }

    async def _remove_external_enduser_mapper(self, alias: str) -> dict[str, Any]:
        mapper_name = "assign-enduser-role"
        mapper_types = {"hardcoded-role-idp-mapper", "oidc-hardcoded-role-idp-mapper"}
        resp = await self._keycloak_request(
            "GET",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
        )
        if resp.status_code == 404:
            return {"status": "skipped", "reason": "Identity provider not found"}
        _raise_keycloak_status(resp)
        mappers = _keycloak_json(resp)
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
            _raise_keycloak_status(delete_resp)
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
        _raise_keycloak_status(resp)
        mappers = _keycloak_json(resp)
        existing = next(
            (mapper for mapper in mappers if isinstance(mapper, dict) and mapper.get("name") == mapper_name),
            None,
        )
        if existing and existing.get("id"):
            update_resp = await self._keycloak_request(
                "PUT",
                f"/identity-provider/instances/{quote(alias, safe='')}/mappers/{existing['id']}",
                json={**payload, "id": existing["id"]},
            )
            if update_resp.status_code not in (200, 204):
                _raise_keycloak_status(update_resp)
            return {"status": "updated", "name": mapper_name}

        create_resp = await self._keycloak_request(
            "POST",
            f"/identity-provider/instances/{quote(alias, safe='')}/mappers",
            json=payload,
        )
        if create_resp.status_code not in (200, 201, 204, 409):
            _raise_keycloak_status(create_resp)
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
        _raise_keycloak_status(resp)
        mappers = _keycloak_json(resp)
        existing = next(
            (mapper for mapper in mappers if isinstance(mapper, dict) and mapper.get("name") == mapper_name),
            None,
        )
        if existing and existing.get("id"):
            update_resp = await self._keycloak_request(
                "PUT",
                f"/clients/{client_uuid}/protocol-mappers/models/{existing['id']}",
                json={**payload, "id": existing["id"]},
            )
            if update_resp.status_code not in (200, 204):
                _raise_keycloak_status(update_resp)
            return {"status": "updated", "name": mapper_name, "client_id": client_id}

        create_resp = await self._keycloak_request(
            "POST",
            f"/clients/{client_uuid}/protocol-mappers/models",
            json=payload,
        )
        if create_resp.status_code not in (200, 201, 204, 409):
            _raise_keycloak_status(create_resp)
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
        _raise_keycloak_status(resp)
        identities = _keycloak_json(resp)
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
        return any(isinstance(identity, dict) and identity.get("identityProvider") == alias for identity in identities)

    async def list_users(
        self,
        first: int = 0,
        max: int = 1000,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        resp = await self._keycloak_request("GET", f"/users?first={first}&max={max}", token=token)
        _raise_keycloak_status(resp)
        return _keycloak_json(resp)

    async def get_user_by_email(self, email: str, token: str | None = None) -> dict[str, Any] | None:
        resp = await self._keycloak_request(
            "GET",
            f"/users?email={quote(email)}&exact=true",
            token=token,
        )
        _raise_keycloak_status(resp)
        users = _keycloak_json(resp)
        return users[0] if users else None

    async def get_user_by_username(self, username: str, token: str | None = None) -> dict[str, Any] | None:
        resp = await self._keycloak_request(
            "GET",
            f"/users?username={quote(username)}&exact=true",
            token=token,
        )
        _raise_keycloak_status(resp)
        users = _keycloak_json(resp)
        return users[0] if users else None

    async def create_user(self, payload: dict[str, Any]) -> str | None:
        resp = await self._keycloak_request("POST", "/users", json=payload)
        if resp.status_code in (200, 201):
            location = resp.headers.get("Location")
            if location:
                return location.split("/")[-1]
        _raise_keycloak_status(resp)
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

    async def get_realm_role(self, role_name: str, token: str | None = None) -> dict[str, Any] | None:
        resp = await self._keycloak_request("GET", f"/roles/{role_name}", token=token)
        if resp.status_code == 404:
            return None
        _raise_keycloak_status(resp)
        role = _keycloak_json(resp)
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
        _raise_keycloak_status(resp)
        roles = _keycloak_json(resp)
        return roles if isinstance(roles, list) else []

    async def get_client_uuid(
        self,
        token: str | None = None,
        client_id: str | None = None,
    ) -> str:
        resolved_client_id = client_id or self.get_client_id()
        cache_key = f"{self.get_realm()}:{resolved_client_id}"
        cached = self._client_uuid_cache.get(cache_key)
        if cached is not None:
            return cached

        resp = await self._keycloak_request(
            "GET",
            f"/clients?clientId={quote(resolved_client_id)}",
            token=token,
        )
        if getattr(resp, "status_code", 200) >= 400:
            _raise_dependency_status(resp)
        clients = _keycloak_json(resp)
        if not isinstance(clients, list):
            raise DependencyResponseError()
        if not clients:
            raise NotFoundError(
                code="keycloak.client_not_found",
                message_key="errors.user_service.keycloak.client_not_found",
                message_params={"client_id": resolved_client_id},
            )

        client = clients[0]
        if not isinstance(client, dict) or not client.get("id"):
            raise DependencyResponseError()

        client_uuid = str(client["id"])
        self._client_uuid_cache[cache_key] = client_uuid
        return client_uuid

    async def set_realm_role(self, keycloak_id: str, role_name: str) -> bool:
        role = await self.get_realm_role(role_name)
        if not role:
            await self.create_realm_role(role_name)
            role = await self.get_realm_role(role_name)
            if not role:
                return False

        current_roles_resp = await self._keycloak_request("GET", f"/users/{keycloak_id}/role-mappings/realm")
        if current_roles_resp.status_code == 404:
            current_roles = []
        else:
            _raise_keycloak_status(current_roles_resp)
            current_roles_payload = _keycloak_json(current_roles_resp)
            current_roles = current_roles_payload if isinstance(current_roles_payload, list) else []

        roles_to_remove = [r for r in current_roles if isinstance(r, dict) and r.get("name") != role_name]

        if roles_to_remove:
            await self._keycloak_request("DELETE", f"/users/{keycloak_id}/role-mappings/realm", json=roles_to_remove)

        await self._keycloak_request("POST", f"/users/{keycloak_id}/role-mappings/realm", json=[role])
        return True

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
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        token_url = f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token"

        def _payload(uri: str) -> dict[str, str]:
            return {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": uri,
                **self._login_client_credentials_payload(),
            }

        resp = await _keycloak_http(client.post(token_url, data=_payload(redirect_uri)))
        if resp.is_success:
            return _keycloak_json(resp)

        # Some frontend flows attach a post-login redirect URI in query params,
        # which can differ from the actual callback URI used for the auth code.
        # Retry with the concrete callback URL when available.
        if fallback_redirect_uri and fallback_redirect_uri != redirect_uri:
            fallback_resp = await _keycloak_http(client.post(token_url, data=_payload(fallback_redirect_uri)))
            if fallback_resp.is_success:
                return _keycloak_json(fallback_resp)
            resp = fallback_resp  # Use fallback response for error details

        # Both attempts failed - extract error detail
        if resp.status_code in {401, 403, 429} or resp.status_code >= 500:
            _raise_dependency_status(resp)
        raise UnauthorizedError()

    async def password_grant(self, username: str, password: str) -> dict[str, Any]:
        """Direct Access Grant — authenticate with username/password against Keycloak.

        Uses the login client (web-client, public) rather than the backend service client,
        because public clients have directAccessGrantsEnabled=true.

        Returns Keycloak token payload { access_token, refresh_token, id_token, expires_in, token_type }.
        Raises ValueError on authentication failure.
        """
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        resp = await _keycloak_http(
            client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": self.get_login_client_id(),
                    "username": username,
                    "password": password,
                    "scope": "openid profile email",
                },
            )
        )
        if resp.is_success:
            payload = _keycloak_json(resp)
            if not isinstance(payload, dict):
                raise DependencyResponseError()
            return payload

        if resp.status_code == 429:
            raise DependencyRateLimitedError()

        try:
            error_body = _keycloak_json(resp)
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
                    raise UnauthorizedError(
                        code="auth.invalid_credentials",
                        message_key="errors.user_service.auth.invalid_credentials",
                        message_params={},
                    )
        except (DependencyResponseError, UnauthorizedError):
            raise
        if resp.status_code in {401, 403}:
            raise DependencyAuthenticationError()
        raise DependencyResponseError()

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

        created_new_user = False
        if user and user.get("id"):
            await self.update_user(str(user["id"]), {**user, **payload})
            keycloak_id = str(user["id"])
        else:
            created_id = await self.create_user(payload)
            if not created_id:
                user = await self.get_user_by_username(username)
                created_id = str(user["id"]) if user and user.get("id") else None
            if not created_id:
                raise DependencyResponseError(
                    message_key="errors.user_service.keycloak.sp_user_create_failed",
                    message_params={},
                )
            keycloak_id = created_id
            created_new_user = True

        await self.add_federated_identity(
            keycloak_id,
            external_user_id=external_subject,
            external_username=username,
        )
        if created_new_user:
            await self.set_realm_role(keycloak_id, "enduser")
        profile = await self.get_user_profile(keycloak_id)
        return profile or {"id": keycloak_id, **payload}

    async def refresh_token_grant(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new set of tokens from Keycloak.

        POSTs to Keycloak's token endpoint with grant_type=refresh_token.
        Returns { access_token, refresh_token, id_token?, expires_in, token_type }.
        Raises ValueError on authentication failure.
        """
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
        resp = await client.post(
            f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                **self._login_client_credentials_payload(),
                "refresh_token": refresh_token,
                "scope": "openid profile email",
            },
        )
        if resp.is_success:
            payload = _keycloak_json(resp)
            if not isinstance(payload, dict):
                raise DependencyResponseError()
            return payload

        if resp.status_code == 429:
            raise DependencyRateLimitedError()

        error_body = _keycloak_json(resp)
        if isinstance(error_body, dict) and error_body.get("error") == "invalid_grant":
            raise UnauthorizedError(
                code="auth.refresh_invalid",
                message_key="errors.user_service.keycloak.token_refresh_failed_status",
                message_params={"status": resp.status_code},
            )
        if resp.status_code in {401, 403}:
            raise DependencyAuthenticationError()
        raise DependencyResponseError()

    # ------------------------------------------------------------------
    # Backchannel logout
    # ------------------------------------------------------------------

    async def backchannel_logout(self, refresh_token: str | None = None, id_token_hint: str | None = None) -> bool:
        client = get_shared_client("keycloak", timeout=_HTTP_TIMEOUT, limits=_HTTP_LIMITS)
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
        resp = await _keycloak_http(
            client.post(
                f"{self.get_base_url()}/realms/{self.get_realm()}/protocol/openid-connect/logout",
                data={**data, **credentials},
            )
        )
        return resp.status_code in (200, 204, 400)


_keycloak_service = KeycloakService()


def get_keycloak_service() -> KeycloakService:
    return _keycloak_service
