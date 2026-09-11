"""Repository for the unified ``agents`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update

from core.db.models.agent import AgentModel
from core.db.repositories.base import BaseRepository
from core.logger import get_logger

logger = get_logger(__name__)


class AgentRepository(BaseRepository):
    """CRUD operations for unified agent records."""

    @staticmethod
    def _to_dict(row: AgentModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "id": str(row.id),
            "legacy_persona_id": row.legacy_persona_id,
            "legacy_assistant_id": str(row.legacy_assistant_id)
            if row.legacy_assistant_id
            else None,
            "legacy_definition_id": str(row.legacy_definition_id)
            if row.legacy_definition_id
            else None,
            "name": row.name,
            "description": row.description,
            "agent_type": row.agent_type,
            "graph_schema": row.graph_schema,
            "brain_type": row.brain_type,
            "memory_type": row.memory_type,
            "system_prompt": row.system_prompt,
            "task_prompt": row.task_prompt,
            "model": row.model,
            "datetime_aware": row.datetime_aware,
            "is_public": row.is_public,
            "llm_model_provider_override": row.llm_model_provider_override,
            "llm_model_version_override": row.llm_model_version_override,
            "starter_messages": row.starter_messages,
            "labels": row.labels,
            "rag_config": row.rag_config or {},
            "mcp_tools": row.mcp_tools or [],
            "mcp_tool_configs": row.mcp_tool_configs or {},
            "sub_agents": row.sub_agents or [],
            "sub_agent_ids": row.sub_agent_ids or [],
            "sub_agent_config_version": row.sub_agent_config_version,
            "supervisor_prompt": row.supervisor_prompt,
            "stages": row.stages or [],
            "pipeline_prompt": row.pipeline_prompt,
            "reflection_prompt": row.reflection_prompt,
            "max_iterations": row.max_iterations,
            "version": row.version,
            "tags": row.tags or [],
            "user_id": row.user_id,
            "is_builtin": row.is_builtin,
            "builtin_key": row.builtin_key,
            "is_active": row.is_active,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _coerce_uuid(value: str | _uuid.UUID) -> _uuid.UUID | None:
        try:
            return value if isinstance(value, _uuid.UUID) else _uuid.UUID(str(value))
        except ValueError:
            return None

    async def list_all(
        self,
        *,
        agent_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return agents ordered by name."""
        async with self._session() as session:
            stmt = select(AgentModel)
            if agent_type:
                stmt = stmt.where(AgentModel.agent_type == agent_type)
            if active_only:
                stmt = stmt.where(AgentModel.is_active)
            stmt = stmt.order_by(AgentModel.name)
            result = await session.execute(stmt)
            return [self._to_dict(row) for row in result.scalars().all()]

    async def get(self, agent_id: str | _uuid.UUID) -> dict[str, Any] | None:
        """Fetch one agent by UUID."""
        coerced_id = self._coerce_uuid(agent_id)
        if coerced_id is None:
            return None
        async with self._session() as session:
            result = await session.execute(select(AgentModel).where(AgentModel.id == coerced_id))
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def create(self, values: dict[str, Any]) -> dict[str, Any]:
        """Create and return one agent."""
        async with self._session() as session:
            row = AgentModel(**values)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return self._to_dict(row)

    async def update(
        self, agent_id: str | _uuid.UUID, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update and return one agent."""
        coerced_id = self._coerce_uuid(agent_id)
        if coerced_id is None:
            return None
        values = {**values, "updated_at": datetime.now(UTC)}
        async with self._session() as session:
            stmt = (
                update(AgentModel)
                .where(AgentModel.id == coerced_id)
                .values(**values)
                .returning(AgentModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_dict(row) if row else None

    async def delete(self, agent_id: str | _uuid.UUID) -> bool:
        """Delete one agent by UUID."""
        coerced_id = self._coerce_uuid(agent_id)
        if coerced_id is None:
            return False
        async with self._session() as session:
            result = await session.execute(delete(AgentModel).where(AgentModel.id == coerced_id))
            return result.rowcount > 0
