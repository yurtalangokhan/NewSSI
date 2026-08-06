"""Repository for SMTP mail configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from core.db.models.mail_config import MailConfigModel
from core.db.models.persona import PersonaModel
from core.db.repositories.base import BaseRepository


class MailConfigRepository(BaseRepository):
    """CRUD operations for the ``mail_config`` table."""

    @staticmethod
    def _parse_id(config_id: str) -> UUID | None:
        try:
            return UUID(config_id)
        except ValueError:
            return None

    @staticmethod
    def _to_dict(row: MailConfigModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "name": row.name,
            "host": row.host,
            "port": row.port,
            "username": row.username,
            "password_encrypted": row.password_encrypted,
            "from_email": row.from_email,
            "from_name": row.from_name,
            "security": row.security,
            "is_active": row.is_active,
            "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(MailConfigModel)
                .where(
                    MailConfigModel.user_id == user_id,
                    MailConfigModel.is_active.is_(True),
                )
                .order_by(MailConfigModel.name)
            )
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def get_by_id(self, user_id: str, config_id: str) -> dict[str, Any] | None:
        parsed_id = self._parse_id(config_id)
        if not parsed_id:
            return None
        async with self._session() as session:
            result = await session.execute(
                select(MailConfigModel).where(
                    MailConfigModel.id == parsed_id,
                    MailConfigModel.user_id == user_id,
                    MailConfigModel.is_active.is_(True),
                )
            )
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def create(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._session() as session:
            row = MailConfigModel(
                **values,
                is_active=True,
                time_created=now,
                time_updated=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return self._to_dict(row)

    async def update(
        self,
        user_id: str,
        config_id: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        parsed_id = self._parse_id(config_id)
        if not parsed_id:
            return None
        cleaned = {key: value for key, value in updates.items() if value is not None}
        if not cleaned:
            return await self.get_by_id(user_id, config_id)
        cleaned["time_updated"] = datetime.now(UTC)
        async with self._session() as session:
            result = await session.execute(
                update(MailConfigModel)
                .where(
                    MailConfigModel.id == parsed_id,
                    MailConfigModel.user_id == user_id,
                    MailConfigModel.is_active.is_(True),
                )
                .values(**cleaned)
                .returning(MailConfigModel)
            )
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def deactivate(self, user_id: str, config_id: str) -> bool:
        parsed_id = self._parse_id(config_id)
        if not parsed_id:
            return False
        async with self._session() as session:
            result = await session.execute(
                update(MailConfigModel)
                .where(
                    MailConfigModel.id == parsed_id,
                    MailConfigModel.user_id == user_id,
                    MailConfigModel.is_active.is_(True),
                )
                .values(is_active=False, time_updated=datetime.now(UTC))
            )
            return result.rowcount > 0

    async def mark_tested(self, user_id: str, config_id: str) -> dict[str, Any] | None:
        return await self.update(user_id, config_id, last_tested_at=datetime.now(UTC))

    async def has_active_bindings(self, user_id: str, config_id: str) -> bool:
        async with self._session() as session:
            persona_result = await session.execute(
                select(PersonaModel.id)
                .where(
                    PersonaModel.user_id == user_id,
                    PersonaModel.mcp_tool_configs["send_email"]["mail_config_id"].as_string()
                    == config_id,
                )
                .limit(1)
            )
            if persona_result.scalar_one_or_none() is not None:
                return True

            from agents.storage.models import AgentDefinitionModel

            definition_result = await session.execute(
                select(AgentDefinitionModel.id)
                .join(PersonaModel, AgentDefinitionModel.persona_id == PersonaModel.id)
                .where(
                    PersonaModel.user_id == user_id,
                    AgentDefinitionModel.is_active.is_(True),
                    AgentDefinitionModel.mcp_tool_configs["send_email"][
                        "mail_config_id"
                    ].as_string()
                    == config_id,
                )
                .limit(1)
            )
            return definition_result.scalar_one_or_none() is not None
