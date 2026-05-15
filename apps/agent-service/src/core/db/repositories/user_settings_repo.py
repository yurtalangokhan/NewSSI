"""Repository for user_settings table operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from core.db.models.user_settings import UserSettingsModel
from core.db.repositories.base import BaseRepository

DEFAULT_USER_SETTINGS: dict[str, Any] = {
    "theme_preference": None,
    "chat_background": None,
    "default_model": None,
    "default_provider_id": None,
    "auto_scroll": True,
    "shortcut_enabled": True,
    "default_app_mode": "AUTO",
    "long_term_memory_enabled": False,
    "extract_memory": True,
    "user_preferences": "",
    "prompt_shortcuts": [],
}


class UserSettingsRepository(BaseRepository):
    """CRUD-like operations for user-scoped settings."""

    @staticmethod
    def _serialize(row: UserSettingsModel) -> dict[str, Any]:
        return {
            "theme_preference": row.theme_preference,
            "chat_background": row.chat_background,
            "default_model": row.default_model,
            "default_provider_id": row.default_provider_id,
            "auto_scroll": bool(row.auto_scroll),
            "shortcut_enabled": bool(row.shortcut_enabled),
            "default_app_mode": row.default_app_mode or "AUTO",
            "long_term_memory_enabled": bool(row.long_term_memory_enabled),
            "extract_memory": bool(row.extract_memory),
            "user_preferences": row.user_preferences or "",
            "prompt_shortcuts": row.prompt_shortcuts or [],
        }

    @staticmethod
    def _normalize_shortcut(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        prompt = str(item.get("prompt", "")).strip()
        content = str(item.get("content", "")).strip()
        if not prompt or not content:
            return None

        raw_id = item.get("id")
        try:
            shortcut_id = int(raw_id)
        except Exception:
            return None

        return {
            "id": shortcut_id,
            "prompt": prompt,
            "content": content,
            "active": bool(item.get("active", True)),
            "is_public": bool(item.get("is_public", False)),
        }

    async def ensure_defaults(self, user_id: str) -> dict[str, Any]:
        return await self.upsert_by_user_id(user_id, {})

    async def upsert_by_user_id(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = set(DEFAULT_USER_SETTINGS.keys())
        normalized_updates = {k: v for k, v in updates.items() if k in allowed}

        if "user_preferences" in normalized_updates and normalized_updates["user_preferences"] is None:
            normalized_updates["user_preferences"] = ""
        if "prompt_shortcuts" in normalized_updates:
            raw_shortcuts = normalized_updates.get("prompt_shortcuts") or []
            normalized_shortcuts = []
            for item in raw_shortcuts:
                normalized = self._normalize_shortcut(item)
                if normalized is not None:
                    normalized_shortcuts.append(normalized)
            normalized_updates["prompt_shortcuts"] = normalized_shortcuts

        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()

            if row is None:
                seed = dict(DEFAULT_USER_SETTINGS)
                seed.update(normalized_updates)
                row = UserSettingsModel(
                    user_id=user_id,
                    theme_preference=seed["theme_preference"],
                    chat_background=seed["chat_background"],
                    default_model=seed["default_model"],
                    auto_scroll=seed["auto_scroll"],
                    shortcut_enabled=seed["shortcut_enabled"],
                    default_app_mode=seed["default_app_mode"],
                    long_term_memory_enabled=seed["long_term_memory_enabled"],
                    extract_memory=seed["extract_memory"],
                    user_preferences=seed["user_preferences"],
                    prompt_shortcuts=seed["prompt_shortcuts"],
                    time_updated=datetime.now(UTC),
                )
                session.add(row)
                await session.flush()
                await session.refresh(row)
                return self._serialize(row)

            for key, value in normalized_updates.items():
                setattr(row, key, value)
            row.time_updated = datetime.now(UTC)
            await session.flush()
            await session.refresh(row)
            return self._serialize(row)

    async def list_prompt_shortcuts(self, user_id: str) -> list[dict[str, Any]]:
        settings = await self.ensure_defaults(user_id)
        shortcuts = settings.get("prompt_shortcuts") or []
        return [s for s in shortcuts if isinstance(s, dict)]

    async def create_prompt_shortcut(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not prompt or not content:
            raise ValueError("prompt and content are required")

        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = UserSettingsModel(user_id=user_id, prompt_shortcuts=[])
                session.add(row)
                await session.flush()

            shortcuts = list(row.prompt_shortcuts or [])
            max_id = 0
            for item in shortcuts:
                if isinstance(item, dict):
                    try:
                        max_id = max(max_id, int(item.get("id", 0)))
                    except Exception:
                        continue

            created = {
                "id": max_id + 1,
                "prompt": prompt,
                "content": content,
                "active": bool(payload.get("active", True)),
                "is_public": bool(payload.get("is_public", False)),
            }
            shortcuts.append(created)
            row.prompt_shortcuts = shortcuts
            row.time_updated = datetime.now(UTC)
            await session.flush()
            return created

    async def update_prompt_shortcut(
        self,
        user_id: str,
        prompt_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None

            shortcuts = list(row.prompt_shortcuts or [])
            for idx, item in enumerate(shortcuts):
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get("id", 0))
                except Exception:
                    continue

                if item_id != prompt_id:
                    continue

                updated = dict(item)
                if "prompt" in payload:
                    updated["prompt"] = str(payload.get("prompt", "")).strip()
                if "content" in payload:
                    updated["content"] = str(payload.get("content", "")).strip()
                if "active" in payload:
                    updated["active"] = bool(payload.get("active"))
                if "is_public" in payload:
                    updated["is_public"] = bool(payload.get("is_public"))

                normalized = self._normalize_shortcut(updated)
                if normalized is None:
                    raise ValueError("prompt and content cannot be empty")

                shortcuts[idx] = normalized
                row.prompt_shortcuts = shortcuts
                row.time_updated = datetime.now(UTC)
                await session.flush()
                return normalized

            return None

    async def delete_prompt_shortcut(self, user_id: str, prompt_id: int) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(UserSettingsModel).where(UserSettingsModel.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False

            shortcuts = list(row.prompt_shortcuts or [])
            filtered = []
            removed = False
            for item in shortcuts:
                if not isinstance(item, dict):
                    continue
                try:
                    item_id = int(item.get("id", 0))
                except Exception:
                    filtered.append(item)
                    continue

                if item_id == prompt_id:
                    removed = True
                    continue
                filtered.append(item)

            if not removed:
                return False

            row.prompt_shortcuts = filtered
            row.time_updated = datetime.now(UTC)
            await session.flush()
            return True
