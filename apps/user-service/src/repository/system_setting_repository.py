from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from src.core.database.models import SystemSettingModel

from .base_repository import BaseRepository


class SystemSettingRepository(BaseRepository):
    async def get_value(self, key: str) -> dict[str, Any]:
        try:
            async with self._session() as session:
                result = await session.execute(
                    select(SystemSettingModel).where(SystemSettingModel.key == key)
                )
                setting = result.scalar_one_or_none()
                return dict(setting.value) if setting else {}
        except (ProgrammingError, DBAPIError) as exc:
            if _is_missing_system_settings_table(exc):
                return {}
            raise

    async def set_value(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        async with self._session() as session:
            result = await session.execute(
                select(SystemSettingModel).where(SystemSettingModel.key == key)
            )
            setting = result.scalar_one_or_none()
            if setting:
                setting.value = value
            else:
                setting = SystemSettingModel(key=key, value=value)
                session.add(setting)
            await session.flush()
            await session.refresh(setting)
            return dict(setting.value)


def _is_missing_system_settings_table(exc: Exception) -> bool:
    message = str(exc).lower()
    return "system_settings" in message and (
        "does not exist" in message
        or "undefinedtable" in message
        or "undefined table" in message
        or "no such table" in message
    )
