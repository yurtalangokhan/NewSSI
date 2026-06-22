"""Repository for agent storage operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update

from agents.storage.models import AgentDefinitionModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AgentDefinitionRepository(BaseRepository):
    """Repository for AgentDefinition CRUD operations."""

    async def create(
        self,
        name: str,
        agent_type: str = "dynamic",
        description: str | None = None,
        graph_schema: str = "zero_shot",
        brain_type: str = "llm",
        memory_type: str = "none",
        system_prompt: str | None = None,
        model: str | None = None,
        mcp_tools: list | None = None,
        rag_config: dict | None = None,
        sub_agents: list | None = None,
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
                agent_type=agent_type,
                description=description,
                graph_schema=graph_schema,
                brain_type=brain_type,
                memory_type=memory_type,
                system_prompt=system_prompt,
                model=model,
                mcp_tools=mcp_tools or [],
                rag_config=rag_config or {},
                sub_agents=sub_agents or [],
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
                stmt = stmt.where(AgentDefinitionModel.is_active == True)

            stmt = stmt.order_by(AgentDefinitionModel.name)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update(
        self,
        id: UUID,
        updates: dict[str, Any],
    ) -> AgentDefinitionModel | None:
        """Update an agent definition."""
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

