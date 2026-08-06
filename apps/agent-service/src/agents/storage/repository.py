"""Repository for agent storage operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, delete, select, update

from agents.storage.models import AgentDefinitionModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AgentDefinitionRepository(BaseRepository):
    """Repository for AgentDefinition CRUD operations."""

    @staticmethod
    def _serialize_sub_agent_ids(sub_agent_ids: list | None) -> list[str]:
        """Serialize UUID-like values for JSON storage."""
        return [str(sub_id) for sub_id in (sub_agent_ids or [])]

    async def create(
        self,
        name: str,
        persona_id: int | None = None,
        agent_type: str = "dynamic",
        description: str | None = None,
        graph_schema: str = "zero_shot",
        brain_type: str = "llm",
        memory_type: str = "none",
        system_prompt: str | None = None,
        model: str | None = None,
        mcp_tools: list | None = None,
        mcp_tool_configs: dict | None = None,
        rag_config: dict | None = None,
        sub_agents: list | None = None,
        sub_agent_ids: list | None = None,
        supervisor_prompt: str | None = None,
        stages: list | None = None,
        pipeline_prompt: str | None = None,
        reflection_prompt: str | None = None,
        max_iterations: int = 3,
        tags: list | None = None,
        version: str = "1.0.0",
    ) -> AgentDefinitionModel:
        """Create a new agent definition."""
        async with self._session() as session:
            definition = AgentDefinitionModel(
                name=name,
                persona_id=persona_id,
                agent_type=agent_type,
                description=description,
                graph_schema=graph_schema,
                brain_type=brain_type,
                memory_type=memory_type,
                system_prompt=system_prompt,
                model=model,
                mcp_tools=mcp_tools or [],
                mcp_tool_configs=mcp_tool_configs or {},
                rag_config=rag_config or {},
                sub_agents=sub_agents or [],
                sub_agent_ids=self._serialize_sub_agent_ids(sub_agent_ids),
                supervisor_prompt=supervisor_prompt,
                stages=stages or [],
                pipeline_prompt=pipeline_prompt,
                reflection_prompt=reflection_prompt,
                max_iterations=max_iterations,
                tags=tags or [],
                version=version,
            )
            session.add(definition)
            await session.flush()
            await session.refresh(definition)
            return definition

    async def get_by_name(self, name: str) -> AgentDefinitionModel | None:
        """Get agent definition by name."""
        async with self._session() as session:
            stmt = select(AgentDefinitionModel).where(AgentDefinitionModel.name == name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_id(self, id: UUID) -> AgentDefinitionModel | None:
        """Get agent definition by ID."""
        async with self._session() as session:
            stmt = select(AgentDefinitionModel).where(AgentDefinitionModel.id == id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_persona_id(self, persona_id: int) -> AgentDefinitionModel | None:
        """Get the dynamic agent definition attached to a persona."""
        async with self._session() as session:
            stmt = select(AgentDefinitionModel).where(AgentDefinitionModel.persona_id == persona_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_all(
        self,
        agent_type: str | None = None,
        graph_schema: str | None = None,
        active_only: bool = True,
    ) -> list[AgentDefinitionModel]:
        """List all agent definitions."""
        async with self._session() as session:
            stmt = select(AgentDefinitionModel)

            if agent_type:
                stmt = stmt.where(AgentDefinitionModel.agent_type == agent_type)
            if graph_schema:
                stmt = stmt.where(AgentDefinitionModel.graph_schema == graph_schema)
            if active_only:
                stmt = stmt.where(AgentDefinitionModel.is_active)

            stmt = stmt.order_by(AgentDefinitionModel.name)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(
        self,
        id: UUID,
        updates: dict[str, Any],
    ) -> AgentDefinitionModel | None:
        """Update an agent definition."""
        if "sub_agent_ids" in updates:
            updates = {
                **updates,
                "sub_agent_ids": self._serialize_sub_agent_ids(updates.get("sub_agent_ids")),
            }

        async with self._session() as session:
            stmt = (
                update(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == id)
                .values(**updates)
                .returning(AgentDefinitionModel)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def delete(self, id: UUID) -> bool:
        """Delete an agent definition."""
        async with self._session() as session:
            stmt = delete(AgentDefinitionModel).where(AgentDefinitionModel.id == id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def activate(self, id: UUID) -> bool:
        """Activate an agent definition."""
        async with self._session() as session:
            stmt = (
                update(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == id)
                .values(is_active=True)
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def deactivate(self, id: UUID) -> bool:
        """Deactivate an agent definition."""
        async with self._session() as session:
            stmt = (
                update(AgentDefinitionModel)
                .where(AgentDefinitionModel.id == id)
                .values(is_active=False)
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def find_agents_by_sub_agent_id(self, sub_agent_id: UUID) -> list[UUID]:
        """
        Find all agents that reference sub_agent_id in their sub_agent_ids.

        Returns:
            List of agent UUIDs that have sub_agent_id in their sub_agent_ids
        """
        async with self._session() as session:
            # For PostgreSQL JSON array containment check
            # We need to check if sub_agent_id is in the sub_agent_ids JSON array
            stmt = select(AgentDefinitionModel.id).where(
                cast(AgentDefinitionModel.sub_agent_ids, String).contains(str(sub_agent_id))
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def find_agents_by_sub_agent_ids(
        self, sub_agent_ids: list[UUID]
    ) -> list[AgentDefinitionModel]:
        """
        Find all agents referencing any of the given IDs.

        Returns:
            List of agents that reference at least one of the given IDs
        """
        if not sub_agent_ids:
            return []

        async with self._session() as session:
            # Build a condition that checks if any sub_agent_id is in the array
            conditions = [
                cast(AgentDefinitionModel.sub_agent_ids, String).contains(str(sub_id))
                for sub_id in sub_agent_ids
            ]

            # OR condition: matches any
            from sqlalchemy import or_

            stmt = select(AgentDefinitionModel).where(or_(*conditions))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_composition_depth(self, agent_id: UUID) -> int:
        """
        Recursively calculate max composition depth for an agent.

        Depth is the maximum nesting level of sub-agents.
        A leaf agent (no sub-agents) has depth 0.
        An agent with leaf sub-agents has depth 1.

        Returns:
            Max depth, or -1 if circular dependency detected
        """
        return await self._calculate_depth_recursive(agent_id, set())

    async def _calculate_depth_recursive(self, agent_id: UUID, visited: set[UUID]) -> int:
        """Internal recursive depth calculation with cycle detection."""
        if agent_id in visited:
            return -1  # Circular dependency

        visited.add(agent_id)

        agent = await self.get_by_id(agent_id)
        if not agent or not agent.sub_agent_ids:
            return 0

        max_depth = 0
        for sub_id in agent.sub_agent_ids:
            depth = await self._calculate_depth_recursive(sub_id, visited.copy())
            if depth == -1:
                return -1  # Propagate circular error
            max_depth = max(max_depth, depth + 1)

        return max_depth
