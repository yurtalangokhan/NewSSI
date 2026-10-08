from typing import Any
import uuid

from error_contract import UnauthorizedError
from localization import t

from src.service import get_user_settings_service

from .base import BaseController


class SettingsController(BaseController):
    def __init__(self):
        self.service = get_user_settings_service()

    @staticmethod
    def _user_id(user_id: uuid.UUID | str) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        try:
            return uuid.UUID(user_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise UnauthorizedError() from exc

    async def get_settings(self, user_id: uuid.UUID | str) -> dict[str, Any]:
        return await self.service.get_settings(self._user_id(user_id))

    async def update_settings(self, user_id: uuid.UUID | str, **updates: Any) -> dict[str, Any]:
        return await self.service.update_settings(self._user_id(user_id), **updates)

    async def create_prompt_shortcut(self, user_id: uuid.UUID | str, shortcut: dict[str, Any]) -> dict[str, Any]:
        return await self.service.create_prompt_shortcut(self._user_id(user_id), shortcut)

    async def update_prompt_shortcut(
        self, user_id: uuid.UUID | str, shortcut_id: int, **updates: Any
    ) -> dict[str, Any]:
        return await self.service.update_prompt_shortcut(self._user_id(user_id), shortcut_id, **updates)

    async def delete_prompt_shortcut(self, user_id: uuid.UUID | str, shortcut_id: int) -> dict[str, str]:
        await self.service.delete_prompt_shortcut(self._user_id(user_id), shortcut_id)
        return {"message": t("settings.shortcut_deleted")}


_settings_controller: SettingsController | None = None


def get_settings_controller() -> SettingsController:
    global _settings_controller
    if _settings_controller is None:
        _settings_controller = SettingsController()
    return _settings_controller
