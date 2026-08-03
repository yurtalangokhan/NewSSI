"""Persona repository — typed CRUD for the ``persona`` table."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update

from core.db.models.persona import PersonaModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PersonaRepository(BaseRepository):
    """CRUD operations on the ``persona`` table."""

    @staticmethod
    def _to_dict(row: PersonaModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "system_prompt": row.system_prompt,
            "task_prompt": row.task_prompt,
            "datetime_aware": row.datetime_aware,
            "is_public": row.is_public,
            "llm_model_provider_override": row.llm_model_provider_override,
            "llm_model_version_override": row.llm_model_version_override,
            "starter_messages": row.starter_messages,
            "labels": row.labels,
            "user_id": row.user_id,
            "is_builtin": row.is_builtin,
            "builtin_key": row.builtin_key,
            "base_agent": row.base_agent,
            "mcp_tools": row.mcp_tools,
            "mcp_tool_configs": row.mcp_tool_configs or {},
            "rag_config": row.rag_config,
            "long_term_memory": bool(row.long_term_memory),
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def get(self, persona_id: int) -> dict[str, Any] | None:
        """Return a persona by ID."""
        async with self._session() as session:
            stmt = select(PersonaModel).where(PersonaModel.id == persona_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_builtin_key(self, builtin_key: str) -> dict[str, Any] | None:
        """Return a persona by its builtin_key (maps to agents.py keys)."""
        async with self._session() as session:
            stmt = select(PersonaModel).where(
                PersonaModel.builtin_key == builtin_key,
                PersonaModel.is_builtin.is_(True),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_all(self, include_builtin: bool = True) -> list[dict[str, Any]]:
        """Return all personas (custom only, or custom + builtin)."""
        async with self._session() as session:
            if include_builtin:
                stmt = select(PersonaModel).order_by(PersonaModel.id)
            else:
                stmt = (
                    select(PersonaModel)
                    .where(PersonaModel.is_builtin.is_(False))
                    .order_by(PersonaModel.id)
                )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all custom personas for a user."""
        async with self._session() as session:
            stmt = (
                select(PersonaModel)
                .where(
                    PersonaModel.user_id == user_id,
                    PersonaModel.is_builtin.is_(False),
                )
                .order_by(PersonaModel.id)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def create(
        self,
        name: str,
        description: str = "",
        system_prompt: str = "",
        task_prompt: str = "",
        user_id: str = "dev-user",
        is_builtin: bool = False,
        builtin_key: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Insert a new persona and return it."""
        now = datetime.now(UTC)
        async with self._session() as session:
            row = PersonaModel(
                name=name,
                description=description,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                user_id=user_id,
                is_builtin=is_builtin,
                builtin_key=builtin_key,
                time_created=now,
                time_updated=now,
                **extra,
            )
            session.add(row)
            await session.flush()
            # Eagerly load all columns before the session closes
            result = self._to_dict(row)
        return result

    async def update(
        self,
        persona_id: int,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Update fields on a persona."""
        allowed = {
            "name",
            "description",
            "system_prompt",
            "task_prompt",
            "datetime_aware",
            "is_public",
            "llm_model_provider_override",
            "llm_model_version_override",
            "starter_messages",
            "labels",
            "base_agent",
            "mcp_tools",
            "mcp_tool_configs",
            "rag_config",
            "long_term_memory",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get(persona_id)

        updates["time_updated"] = datetime.now(UTC)

        async with self._session() as session:
            stmt = update(PersonaModel).where(PersonaModel.id == persona_id).values(**updates)
            await session.execute(stmt)
        return await self.get(persona_id)

    async def delete(self, persona_id: int) -> bool:
        """Delete a persona. Returns True if removed."""
        async with self._session() as session:
            stmt = delete(PersonaModel).where(PersonaModel.id == persona_id)
            result = await session.execute(stmt)
            return result.rowcount > 0
