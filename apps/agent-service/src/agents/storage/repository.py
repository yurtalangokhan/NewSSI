"""Repository for agent storage operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.repositories.base import BaseRepository
from agents.storage.models import (
    AgentDefinitionModel,
    AgentInstanceModel,
    SubAgentModel,
    PipelineStageModel,
)

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


class AgentInstanceRepository(BaseRepository):
    """Repository for AgentInstance CRUD operations."""

    async def create(
        self,
        definition_id: UUID,
        user_id: str | None = None,
        runtime_config: dict | None = None,
    ) -> AgentInstanceModel:
        """Create a new agent instance."""
        async with self._session() as session:
            model = AgentInstanceModel(
                definition_id=definition_id,
                user_id=user_id,
                runtime_config=runtime_config or {},
            )
            session.add(model)
            return model

    async def get_by_id(self, id: UUID) -> AgentInstanceModel | None:
        """Get agent instance by ID."""
        async with self._session() as session:
            stmt = select(AgentInstanceModel).where(AgentInstanceModel.id == id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_for_user(
        self,
        definition_id: UUID,
        user_id: str,
    ) -> AgentInstanceModel | None:
        """Get agent instance for a user."""
        async with self._session() as session:
            stmt = select(AgentInstanceModel).where(
                AgentInstanceModel.definition_id == definition_id,
                AgentInstanceModel.user_id == user_id,
                AgentInstanceModel.is_active == True,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_state(self, id: UUID, state: dict) -> bool:
        """Update agent state/checkpoint."""
        async with self._session() as session:
            stmt = update(AgentInstanceModel).where(AgentInstanceModel.id == id).values(state=state)
            result = await session.execute(stmt)
            return result.rowcount > 0


class SubAgentRepository(BaseRepository):
    """Repository for SubAgent CRUD operations."""

    async def create_for_manager(
        self,
        manager_id: UUID,
        name: str,
        system_prompt: str | None = None,
        mcp_tools: list | None = None,
        model: str | None = None,
        order_index: int = 0,
    ) -> SubAgentModel:
        """Create a sub-agent for a manager."""
        async with self._session() as session:
            model = SubAgentModel(
                manager_id=manager_id,
                name=name,
                system_prompt=system_prompt,
                mcp_tools=mcp_tools or [],
                model=model,
                order_index=order_index,
            )
            session.add(model)
            return model

    async def get_for_manager(
        self,
        manager_id: UUID,
    ) -> list[SubAgentModel]:
        """Get all sub-agents for a manager."""
        async with self._session() as session:
            stmt = (
                select(SubAgentModel)
                .where(SubAgentModel.manager_id == manager_id)
                .order_by(SubAgentModel.order_index)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def delete_for_manager(self, manager_id: UUID) -> bool:
        """Delete all sub-agents for a manager."""
        async with self._session() as session:
            stmt = delete(SubAgentModel).where(SubAgentModel.manager_id == manager_id)
            result = await session.execute(stmt)
            return result.rowcount > 0


class PipelineStageRepository(BaseRepository):
    """Repository for PipelineStage CRUD operations."""

    async def create_for_pipeline(
        self,
        pipeline_id: UUID,
        name: str,
        system_prompt: str | None = None,
        mcp_tools: list | None = None,
        model: str | None = None,
        stage_order: int = 0,
        on_error: str = "abort",
        retry_count: int = 2,
    ) -> PipelineStageModel:
        """Create a stage for a pipeline."""
        async with self._session() as session:
            model = PipelineStageModel(
                pipeline_id=pipeline_id,
                name=name,
                system_prompt=system_prompt,
                mcp_tools=mcp_tools or [],
                model=model,
                stage_order=stage_order,
                on_error=on_error,
                retry_count=retry_count,
            )
            session.add(model)
            return model

    async def get_for_pipeline(
        self,
        pipeline_id: UUID,
    ) -> list[PipelineStageModel]:
        """Get all stages for a pipeline."""
        async with self._session() as session:
            stmt = (
                select(PipelineStageModel)
                .where(PipelineStageModel.pipeline_id == pipeline_id)
                .order_by(PipelineStageModel.stage_order)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
