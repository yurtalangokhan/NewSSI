from typing import Any
import uuid

from cryptography.fernet import InvalidToken

from src.service import get_user_connector_config_service

from .base import BaseController


class UserConnectorConfigController(BaseController):
    def __init__(self):
        self.service = get_user_connector_config_service()

    async def list_configs(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        return await self.service.list_for_user(user_id)

    async def create_config(
        self,
        user_id: uuid.UUID,
        connector_name: str,
        name: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.service.create(user_id, connector_name, name, config)

    async def get_config(self, user_id: uuid.UUID, config_id: uuid.UUID) -> dict[str, Any]:
        try:
            result = await self.service.get(config_id, user_id)
        except (InvalidToken, ValueError):
            self._raise_conflict("connector_config.unreadable")
        if not result:
            self._raise_not_found("connector_config.not_found")
        return result

    async def update_config(
        self,
        user_id: uuid.UUID,
        config_id: uuid.UUID,
        *,
        name: str | None,
        config: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = await self.service.update(config_id, user_id, name=name, config=config)
        if not result:
            self._raise_not_found("connector_config.not_found")
        return result

    async def delete_config(self, user_id: uuid.UUID, config_id: uuid.UUID) -> None:
        if not await self.service.delete(config_id, user_id):
            self._raise_not_found("connector_config.not_found")


_user_connector_config_controller: UserConnectorConfigController | None = None


def get_user_connector_config_controller() -> UserConnectorConfigController:
    global _user_connector_config_controller
    if _user_connector_config_controller is None:
        _user_connector_config_controller = UserConnectorConfigController()
    return _user_connector_config_controller
