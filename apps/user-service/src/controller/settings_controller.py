import uuid
from typing import Any

from src.service import get_user_settings_service

from .base import BaseController


class SettingsController(BaseController):
    def __init__(self):
        self.service = get_user_settings_service()

    async def get_settings(self, user_id: uuid.UUID) -> dict[str, Any]:
        return await self.service.get_settings(user_id)

    async def update_settings(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        return await self.service.update_settings(user_id, **updates)

    async def create_prompt_shortcut(self, user_id: uuid.UUID, shortcut: dict[str, Any]) -> dict[str, Any]:
        return await self.service.create_prompt_shortcut(user_id, shortcut)

    async def update_prompt_shortcut(self, user_id: uuid.UUID, shortcut_id: int, **updates: Any) -> dict[str, Any]:
        result = await self.service.update_prompt_shortcut(user_id, shortcut_id, **updates)
        if not result:
            self._raise_not_found("Shortcut not found")
        return result

    async def delete_prompt_shortcut(self, user_id: uuid.UUID, shortcut_id: int) -> dict[str, str]:
        success = await self.service.delete_prompt_shortcut(user_id, shortcut_id)
        if not success:
            self._raise_not_found("Shortcut not found")
        return {"message": "Shortcut deleted"}


_settings_controller: SettingsController | None = None


def get_settings_controller() -> SettingsController:
    global _settings_controller
    if _settings_controller is None:
        _settings_controller = SettingsController()
    return _settings_controller
