from typing import Any

from config_manager import env
from cryptography.fernet import Fernet, InvalidToken
from error_contract import ConfigurationError, DependencyUnavailableError, render_error_message
from security import reveal_secret

from src.core.security.encryption import SecretScope, get_cipher
from src.repository import SystemSettingRepository
from src.schema.system_settings import KeycloakConfigUpdate, KeycloakRealmSessionUpdate
from src.service.keycloak_service import get_keycloak_service

KEYCLOAK_SETTINGS_KEY = "keycloak"
SECRET_FIELDS = {
    "KEYCLOAK_ADMIN_PASSWORD",
    "KEYCLOAK_CLIENT_SECRET",
    "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
}


def _configured_value(*values: Any) -> str | None:
    """Return the first non-blank value, unwrapping ``SecretStr`` as it goes.

    Without the unwrap a ``SecretStr`` stringifies to its mask, which is truthy
    and would be returned as though it were the configured secret.
    """
    for value in values:
        revealed = reveal_secret(value)
        if revealed:
            return revealed
    return None


def _fernet() -> Fernet:
    """The cipher for secrets inside persisted system settings.

    Scoped to SYSTEM_SETTINGS_ENCRYPTION_KEY, so a leak of the API-key cipher
    does not expose these. Key validation lives in core.security.encryption.
    """
    return get_cipher(SecretScope.SYSTEM_SETTINGS)


def _encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError) as exc:
        raise ConfigurationError() from exc


class SystemSettingsService:
    def __init__(self):
        self.settings = env
        self.env = env
        self.repo = SystemSettingRepository()
        self.keycloak = get_keycloak_service()

    async def load_runtime_settings(self) -> None:
        persisted = await self.repo.get_value(KEYCLOAK_SETTINGS_KEY)
        self.keycloak.set_runtime_settings(self._runtime_settings_from_persisted(persisted))

    async def get_keycloak_settings(self) -> dict[str, Any]:
        await self.load_runtime_settings()
        persisted = await self.repo.get_value(KEYCLOAK_SETTINGS_KEY)
        external_config = self._external_keycloak_config(persisted)
        status = await self._external_identity_provider_status()
        realm_config = await self._safe_realm_session_config()

        return {
            "keycloak": {
                "realm": self.keycloak.get_realm(),
                "base_url": self._safe_keycloak_base_url(),
                "issuer_url": self.keycloak.get_issuer_url(),
                "admin": self._plain_config("KEYCLOAK_ADMIN", persisted, self.env.KEYCLOAK_ADMIN),
                "admin_password_configured": bool(
                    self._plain_config(
                        "KEYCLOAK_ADMIN_PASSWORD",
                        persisted,
                        self.env.KEYCLOAK_ADMIN_PASSWORD,
                    )
                ),
                "client_id": self.keycloak.get_client_id(),
                "login_client_id": self.keycloak.get_login_client_id(),
                "client_secret_configured": bool(self.keycloak.get_client_secret()),
                "admin_access_configured": self.keycloak.has_admin_access(),
                "realm_session": realm_config,
            },
            "external_keycloak": {
                **external_config,
                "identity_provider": status,
            },
        }

    async def update_keycloak_settings(self, payload: KeycloakConfigUpdate) -> dict[str, Any]:
        current = await self.repo.get_value(KEYCLOAK_SETTINGS_KEY)
        updates = payload.model_dump(exclude_unset=True)

        mapping = {
            "keycloak_base_url": "KEYCLOAK_BASE_URL",
            "keycloak_issuer_url": "KEYCLOAK_ISSUER_URL",
            "keycloak_realm": "KEYCLOAK_REALM",
            "keycloak_admin": "KEYCLOAK_ADMIN",
            "keycloak_admin_password": "KEYCLOAK_ADMIN_PASSWORD",
            "keycloak_client_id": "KEYCLOAK_USER_SERVICE_CLIENT_ID",
            "keycloak_login_client_id": "KEYCLOAK_LOGIN_CLIENT_ID",
            "keycloak_client_secret": "KEYCLOAK_CLIENT_SECRET",
            "external_keycloak": "EXTERNAL_KEYCLOAK",
            "external_keycloak_alias": "EXTERNAL_KEYCLOAK_ALIAS",
            "external_keycloak_display_name": "EXTERNAL_KEYCLOAK_DISPLAY_NAME",
            "external_keycloak_base_url": "EXTERNAL_KEYCLOAK_BASE_URL",
            "external_keycloak_issuer_url": "EXTERNAL_KEYCLOAK_ISSUER_URL",
            "external_keycloak_backend_issuer_url": "EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL",
            "external_keycloak_realm": "EXTERNAL_KEYCLOAK_REALM",
            "external_keycloak_client_id": "EXTERNAL_KEYCLOAK_CLIENT_ID",
            "external_keycloak_client_secret": "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
        }

        for field, key in mapping.items():
            if field not in updates:
                continue
            value = updates[field]
            if isinstance(value, str):
                value = value.strip()
            if key in SECRET_FIELDS:
                if value:
                    current[f"{key}_ENCRYPTED"] = _encrypt_secret(str(value))
                continue
            current[key] = value

        saved = await self.repo.set_value(KEYCLOAK_SETTINGS_KEY, current)
        self.keycloak.set_runtime_settings(self._runtime_settings_from_persisted(saved))
        return await self.get_keycloak_settings()

    async def get_realm_session_settings(self) -> dict[str, Any]:
        return await self._safe_realm_session_config()

    async def update_realm_session_settings(self, payload: KeycloakRealmSessionUpdate) -> dict[str, Any]:
        updates = {
            "accessTokenLifespan": payload.access_token_lifespan,
            "ssoSessionIdleTimeout": payload.sso_session_idle_timeout,
            "ssoSessionMaxLifespan": payload.sso_session_max_lifespan,
            "clientSessionMaxLifespan": payload.client_session_max_lifespan,
        }
        cleaned = {key: value for key, value in updates.items() if value is not None}
        if not cleaned:
            return await self.get_realm_session_settings()
        realm_config = await self.keycloak.update_realm_configuration(cleaned)
        return self._realm_session_response(realm_config)

    async def sync_external_identity_provider(self) -> dict[str, Any]:
        await self.load_runtime_settings()
        result = await self.keycloak.ensure_external_identity_provider()
        settings = await self.get_keycloak_settings()
        return {"result": result, "settings": settings}

    def _runtime_settings_from_persisted(self, persisted: dict[str, Any]) -> dict[str, Any]:
        runtime = {
            key: value
            for key, value in persisted.items()
            if not key.endswith("_ENCRYPTED") and value is not None and value != ""
        }
        for secret_key in SECRET_FIELDS:
            decrypted = _decrypt_secret(persisted.get(f"{secret_key}_ENCRYPTED"))
            if decrypted:
                runtime[secret_key] = decrypted
        return runtime

    def _external_keycloak_config(self, persisted: dict[str, Any]) -> dict[str, Any]:
        client_secret = self._plain_config(
            "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
            persisted,
            self.env.EXTERNAL_KEYCLOAK_CLIENT_SECRET,
            self.settings.EXTERNAL_KEYCLOAK_CLIENT_SECRET,
        )
        return {
            "enabled": self.keycloak.is_external_keycloak(),
            "source": self._source_for(persisted, "EXTERNAL_KEYCLOAK"),
            "alias": self.keycloak.get_external_keycloak_alias(),
            "display_name": self._plain_config(
                "EXTERNAL_KEYCLOAK_DISPLAY_NAME",
                persisted,
                self.env.EXTERNAL_KEYCLOAK_DISPLAY_NAME,
                self.settings.EXTERNAL_KEYCLOAK_DISPLAY_NAME,
            ),
            "issuer_url": self._safe_external_issuer_url(),
            "backend_issuer_url": self._plain_config(
                "EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL",
                persisted,
                self.env.EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL,
                self.settings.EXTERNAL_KEYCLOAK_BACKEND_ISSUER_URL,
            ),
            "base_url": self._plain_config(
                "EXTERNAL_KEYCLOAK_BASE_URL",
                persisted,
                self.env.EXTERNAL_KEYCLOAK_BASE_URL,
                self.settings.EXTERNAL_KEYCLOAK_BASE_URL,
            ),
            "realm": self._plain_config(
                "EXTERNAL_KEYCLOAK_REALM",
                persisted,
                self.env.EXTERNAL_KEYCLOAK_REALM,
                self.settings.EXTERNAL_KEYCLOAK_REALM,
            ),
            "client_id": self._plain_config(
                "EXTERNAL_KEYCLOAK_CLIENT_ID",
                persisted,
                self.env.EXTERNAL_KEYCLOAK_CLIENT_ID,
                self.settings.EXTERNAL_KEYCLOAK_CLIENT_ID,
            ),
            "client_secret_configured": bool(client_secret),
        }

    def _plain_config(self, key: str, persisted: dict[str, Any], *fallbacks: Any) -> Any:
        if key in SECRET_FIELDS:
            return _decrypt_secret(persisted.get(f"{key}_ENCRYPTED")) or _configured_value(*fallbacks)
        if key in persisted:
            return persisted[key]
        return _configured_value(*fallbacks)

    def _source_for(self, persisted: dict[str, Any], key: str) -> str:
        return "database" if key in persisted or f"{key}_ENCRYPTED" in persisted else ".env"

    def _safe_keycloak_base_url(self) -> str | None:
        try:
            return self.keycloak.get_base_url()
        except (ValueError, ConfigurationError):
            return None

    def _safe_external_issuer_url(self) -> str | None:
        try:
            return self.keycloak.get_external_issuer_url()
        except (ValueError, ConfigurationError):
            return None

    async def _safe_realm_session_config(self) -> dict[str, Any]:
        try:
            return self._realm_session_response(await self.keycloak.get_realm_configuration())
        except Exception:
            # This read-only status endpoint reports dependency reachability.
            return {"reachable": False, "error": render_error_message(DependencyUnavailableError())}

    def _realm_session_response(self, realm_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "reachable": True,
            "access_token_lifespan": realm_config.get("accessTokenLifespan"),
            "sso_session_idle_timeout": realm_config.get("ssoSessionIdleTimeout"),
            "sso_session_max_lifespan": realm_config.get("ssoSessionMaxLifespan"),
            "client_session_max_lifespan": realm_config.get("clientSessionMaxLifespan"),
        }

    async def _external_identity_provider_status(self) -> dict[str, Any]:
        try:
            return await self.keycloak.get_external_identity_provider_status()
        except Exception:
            # This read-only status endpoint reports dependency reachability.
            return {
                "enabled": self.keycloak.is_external_keycloak(),
                "alias": self.keycloak.get_external_keycloak_alias(),
                "exists": False,
                "reachable": False,
                "provider": None,
                "mapper": None,
                "error": render_error_message(DependencyUnavailableError()),
            }


_system_settings_service_instance: SystemSettingsService | None = None


def get_system_settings_service() -> SystemSettingsService:
    global _system_settings_service_instance
    if _system_settings_service_instance is None:
        _system_settings_service_instance = SystemSettingsService()
    return _system_settings_service_instance
