import uuid
from typing import Any

from sqlalchemy import delete, select

from src.core.database.models import UserSettingsModel

from .base_repository import BaseRepository


class UserSettingsRepository(BaseRepository):
    DEFAULT_SETTINGS = {
        "auto_scroll": True,
        "shortcut_enabled": True,
        "default_app_mode": "AUTO",
        "memories": [],
        "use_memories": False,
        "enable_memory_tool": False,
        "long_term_memory_enabled": False,
        "extract_memory": True,
        "user_preferences": "",
        "work_role": "",
        "prompt_shortcuts": [],
    }

    async def get_by_user_id(self, user_id: uuid.UUID) -> UserSettingsModel | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def upsert(self, user_id: uuid.UUID, **updates: Any) -> UserSettingsModel:
        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            settings = result.scalar_one_or_none()

            allowed_keys = {
                "theme_preference",
                "chat_background",
                "default_model",
                "default_provider_id",
                "auto_scroll",
                "shortcut_enabled",
                "default_app_mode",
                "memories",
                "use_memories",
                "enable_memory_tool",
                "long_term_memory_enabled",
                "extract_memory",
                "user_preferences",
                "work_role",
                "prompt_shortcuts",
            }
            filtered = {k: v for k, v in updates.items() if k in allowed_keys and v is not None}
            if "user_preferences" in filtered:
                filtered["user_preferences"] = str(filtered["user_preferences"] or "")
            if "work_role" in filtered:
                filtered["work_role"] = str(filtered["work_role"] or "").strip()

            if settings:
                for key, value in filtered.items():
                    setattr(settings, key, value)
            else:
                defaults = {k: v for k, v in self.DEFAULT_SETTINGS.items() if k not in filtered}
                filtered.update(defaults)
                settings = UserSettingsModel(user_id=user_id, **filtered)
                session.add(settings)

            await session.flush()
            await session.refresh(settings)
            return settings

    async def ensure_defaults(self, user_id: uuid.UUID) -> UserSettingsModel:
        return await self.upsert(user_id)

    async def delete(self, user_id: uuid.UUID) -> bool:
        async with self._session() as session:
            result = await session.execute(
                delete(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            return result.rowcount > 0
