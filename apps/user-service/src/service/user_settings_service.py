import uuid
from typing import Any

from src.repository import UserSettingsRepository

_DEFAULT_SETTINGS = {
    "auto_scroll": True,
    "shortcut_enabled": True,
    "default_app_mode": "AUTO",
    "memories": [],
    "use_memories": False,
    "enable_memory_tool": False,
    "user_preferences": "",
    "prompt_shortcuts": [],
}


class UserSettingsService:
    def __init__(self):
        self.repo = UserSettingsRepository()

    async def get_settings(self, user_id: uuid.UUID) -> dict[str, Any]:
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            settings = await self.repo.ensure_defaults(user_id)
        return self._settings_to_dict(settings)

    async def update_settings(self, user_id: uuid.UUID, **updates: Any) -> dict[str, Any]:
        settings = await self.repo.upsert(user_id, **updates)
        return self._settings_to_dict(settings)

    async def ensure_defaults(self, user_id: uuid.UUID) -> dict[str, Any]:
        settings = await self.repo.ensure_defaults(user_id)
        return self._settings_to_dict(settings)

    async def create_prompt_shortcut(self, user_id: uuid.UUID, shortcut: dict[str, Any]) -> dict[str, Any]:
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            settings = await self.repo.ensure_defaults(user_id)

        shortcuts = list(settings.prompt_shortcuts or [])
        new_id = max([s.get("id", 0) for s in shortcuts] + [0]) + 1
        shortcut["id"] = new_id
        shortcuts.append(shortcut)

        await self.repo.upsert(user_id, prompt_shortcuts=shortcuts)
        return shortcut

    async def update_prompt_shortcut(self, user_id: uuid.UUID, shortcut_id: int, **updates: Any) -> dict[str, Any] | None:
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return None

        shortcuts = list(settings.prompt_shortcuts or [])
        for i, s in enumerate(shortcuts):
            if s.get("id") == shortcut_id:
                shortcuts[i] = {**s, **updates}
                await self.repo.upsert(user_id, prompt_shortcuts=shortcuts)
                return shortcuts[i]

        return None

    async def delete_prompt_shortcut(self, user_id: uuid.UUID, shortcut_id: int) -> bool:
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return False

        shortcuts = list(settings.prompt_shortcuts or [])
        filtered = [s for s in shortcuts if s.get("id") != shortcut_id]
        if len(filtered) == len(shortcuts):
            return False

        await self.repo.upsert(user_id, prompt_shortcuts=filtered)
        return True

    def _settings_to_dict(self, settings) -> dict[str, Any]:
        return {
            "id": str(settings.id),
            "user_id": str(settings.user_id),
            "theme_preference": settings.theme_preference,
            "chat_background": settings.chat_background,
            "default_model": settings.default_model,
            "default_provider_id": settings.default_provider_id,
            "auto_scroll": settings.auto_scroll,
            "shortcut_enabled": settings.shortcut_enabled,
            "default_app_mode": settings.default_app_mode,
            "memories": settings.memories or [],
            "use_memories": settings.use_memories,
            "enable_memory_tool": settings.enable_memory_tool,
            "user_preferences": settings.user_preferences or "",
            "prompt_shortcuts": settings.prompt_shortcuts or [],
            "time_created": settings.time_created.isoformat() if settings.time_created else None,
            "time_updated": settings.time_updated.isoformat() if settings.time_updated else None,
        }


_settings_service: UserSettingsService | None = None


def get_user_settings_service() -> UserSettingsService:
    global _settings_service
    if _settings_service is None:
        _settings_service = UserSettingsService()
    return _settings_service
