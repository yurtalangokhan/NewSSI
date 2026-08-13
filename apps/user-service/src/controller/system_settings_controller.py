from typing import Any

from src.schema.system_settings import KeycloakConfigUpdate, KeycloakRealmSessionUpdate

from .base import BaseController


class SystemSettingsController(BaseController):
    def __init__(self):
        from src.service.system_settings_service import get_system_settings_service

        self.service = get_system_settings_service()

    async def get_keycloak_settings(self) -> dict[str, Any]:
        return await self.service.get_keycloak_settings()

    async def update_keycloak_settings(self, payload: KeycloakConfigUpdate) -> dict[str, Any]:
        try:
            return await self.service.update_keycloak_settings(payload)
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def update_realm_session_settings(
        self, payload: KeycloakRealmSessionUpdate
    ) -> dict[str, Any]:
        try:
            return await self.service.update_realm_session_settings(payload)
        except ValueError as e:
            self._raise_bad_request(str(e))
        except Exception as e:
            self._raise_bad_request("system_settings.keycloak_realm_update_failed", error=str(e))

    async def sync_external_identity_provider(self) -> dict[str, Any]:
        try:
            return await self.service.sync_external_identity_provider()
        except ValueError as e:
            self._raise_bad_request(str(e))
        except Exception as e:
            self._raise_bad_request("system_settings.external_keycloak_sync_failed", error=str(e))


_system_settings_controller_instance: SystemSettingsController | None = None


def get_system_settings_controller() -> SystemSettingsController:
    global _system_settings_controller_instance
    if _system_settings_controller_instance is None:
        _system_settings_controller_instance = SystemSettingsController()
    return _system_settings_controller_instance
