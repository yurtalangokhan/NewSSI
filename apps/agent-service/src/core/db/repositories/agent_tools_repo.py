"""Agent Tools repository — typed CRUD for the ``agent_tools`` table."""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.agent_tools import AgentToolsModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AgentToolsRepository(BaseRepository):
    """CRUD operations on the ``agent_tools`` junction table."""

    @staticmethod
    def _to_dict(row: AgentToolsModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "id": str(row.id),
            "agent_id": row.agent_id,
            "tool_id": str(row.tool_id),
            "config": row.config or {},
            "is_active": row.is_active,
            "order_index": row.order_index,
            "time_created": row.time_created.isoformat() if row.time_created else None,
        }

    async def list_by_agent(self, agent_id: int) -> list[dict[str, Any]]:
        """Return all tools for an agent."""
        async with self._session() as session:
            stmt = (
                select(AgentToolsModel)
                .where(
                    AgentToolsModel.agent_id == agent_id,
                    AgentToolsModel.is_active.is_(True),
                )
                .order_by(AgentToolsModel.order_index)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_by_tool(self, tool_id: str) -> list[dict[str, Any]]:
        """Return all agents using a specific tool."""
        async with self._session() as session:
            stmt = (
                select(AgentToolsModel)
                .where(
                    AgentToolsModel.tool_id == tool_id,
                    AgentToolsModel.is_active.is_(True),
                )
                .order_by(AgentToolsModel.agent_id)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def get(self, agent_id: int, tool_id: str) -> dict[str, Any] | None:
        """Get a specific agent-tool binding."""
        async with self._session() as session:
            stmt = select(AgentToolsModel).where(
                AgentToolsModel.agent_id == agent_id,
                AgentToolsModel.tool_id == tool_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def add_tool(
        self,
        agent_id: int,
        tool_id: str,
        config: dict[str, Any] | None = None,
        order_index: int = 0,
    ) -> dict[str, Any]:
        """Add a tool to an agent."""
        async with self._session() as session:
            stmt = (
                pg_insert(AgentToolsModel)
                .values(
                    id=_uuid.uuid4(),
                    agent_id=agent_id,
                    tool_id=tool_id,
                    config=config or {},
                    order_index=order_index,
                )
                .returning(AgentToolsModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def add_tools(
        self,
        agent_id: int,
        tool_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Add multiple tools to an agent."""
        added = []
        async with self._session() as session:
            for idx, tool_id in enumerate(tool_ids):
                stmt = (
                    pg_insert(AgentToolsModel)
                    .values(
                        id=_uuid.uuid4(),
                        agent_id=agent_id,
                        tool_id=tool_id,
                        order_index=idx,
                    )
                    .returning(AgentToolsModel)
                )
                try:
                    result = await session.execute(stmt)
                    row = result.scalar_one_or_none()
                    if row:
                        added.append(self._to_dict(row))
                except Exception as e:
                    logger.warning(f"Failed to add tool {tool_id} to agent {agent_id}: {e}")
        return added

    async def remove_tool(self, agent_id: int, tool_id: str) -> bool:
        """Remove a tool from an agent."""
        async with self._session() as session:
            stmt = delete(AgentToolsModel).where(
                AgentToolsModel.agent_id == agent_id,
                AgentToolsModel.tool_id == tool_id,
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def remove_all_tools(self, agent_id: int) -> int:
        """Remove all tools from an agent."""
        async with self._session() as session:
            stmt = delete(AgentToolsModel).where(AgentToolsModel.agent_id == agent_id)
            result = await session.execute(stmt)
            return result.rowcount

    async def update_config(
        self,
        agent_id: int,
        tool_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update tool config for an agent."""
        async with self._session() as session:
            stmt = (
                update(AgentToolsModel)
                .where(
                    AgentToolsModel.agent_id == agent_id,
                    AgentToolsModel.tool_id == tool_id,
                )
                .values(config=config)
                .returning(AgentToolsModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def reorder_tools(
        self,
        agent_id: int,
        tool_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Reorder tools for an agent."""
        async with self._session() as session:
            for idx, tool_id in enumerate(tool_ids):
                stmt = (
                    update(AgentToolsModel)
                    .where(
                        AgentToolsModel.agent_id == agent_id,
                        AgentToolsModel.tool_id == tool_id,
                    )
                    .values(order_index=idx)
                )
                await session.execute(stmt)

        return await self.list_by_agent(agent_id)
