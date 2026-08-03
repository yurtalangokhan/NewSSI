"""Agent domain service - handles agent registry, definitions, and management."""

import logging
from typing import Any
from uuid import UUID

from models.agents import AgentInfo
from service.CacheInvalidationService import CacheInvalidationService
from service.CompositionValidationService import CompositionValidationService

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent instances and configurations."""

    def __init__(self, agent_registry: dict[str, Any]):
        self._registry = agent_registry

    async def get_agent(self, agent_id: str) -> Any:
        """Get an agent by ID."""
        from agents import get_agent

        return get_agent(agent_id)

    async def get_all_agent_info(self) -> list[AgentInfo]:
        """List all available agents."""
        from agents import get_all_agent_info

        return get_all_agent_info()

    async def load_agent(self, agent_id: str) -> None:
        """Load a lazy agent."""
        from agents import load_agent

        await load_agent(agent_id)

    async def get_default_agent(self) -> str:
        """Get the default agent key."""
        from agents import DEFAULT_AGENT

        return DEFAULT_AGENT


class AgentDefinitionService:
    """
    Service layer for managing AgentDefinition records.

    Wraps AgentDefinitionRepository with business-logic validation
    (schema capability checks, duplicate name detection).

    Includes composition management (sub-agent references).
    """

    def __init__(
        self,
        repository,
        validation_service: CompositionValidationService | None = None,
        cache_service: CacheInvalidationService | None = None,
    ):
        self._repo = repository
        # Lazy-load if not provided
        self._validation_service = validation_service
        self._cache_service = cache_service

    @staticmethod
    def _normalize_graph_schema(
        graph_schema: str,
        mcp_tools: list[str] | None = None,
        rag_config: dict[str, Any] | None = None,
    ) -> str:
        has_rag_tools = any(
            (rag_config or {}).get(key)
            for key in ("document_processing", "knowledge_graph", "collections")
        )
        if graph_schema == "zero_shot" and ((mcp_tools or []) or has_rag_tools):
            return "react"
        return graph_schema

    async def create_agent_definition(
        self,
        name: str,
        persona_id: int | None = None,
        graph_schema: str = "zero_shot",
        brain_type: str = "llm",
        memory_type: str = "none",
        system_prompt: str | None = None,
        model: str | None = None,
        mcp_tools: list[str] | None = None,
        mcp_tool_configs: dict[str, Any] | None = None,
        rag_config: dict[str, Any] | None = None,
        sub_agents: list[dict[str, Any]] | None = None,
        sub_agent_ids: list[UUID] | None = None,
        supervisor_prompt: str | None = None,
        stages: list[dict[str, Any]] | None = None,
        pipeline_prompt: str | None = None,
        reflection_prompt: str | None = None,
        max_iterations: int = 3,
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        from agents.graphs.schemas import get_schema

        graph_schema = self._normalize_graph_schema(
            graph_schema,
            mcp_tools,
            rag_config=rag_config,
        )

        schema = get_schema(graph_schema)
        if not schema:
            raise ValueError(f"Invalid graph schema: {graph_schema}")

        if sub_agents and not schema.supports_sub_agents:
            raise ValueError(f"Schema '{graph_schema}' does not support sub-agents")

        if sub_agent_ids and not schema.supports_sub_agents:
            raise ValueError(f"Schema '{graph_schema}' does not support sub-agents")

        if mcp_tools and not schema.supports_tools:
            raise ValueError(f"Schema '{graph_schema}' does not support tools")

        if sub_agent_ids:
            if not self._validation_service:
                self._validation_service = CompositionValidationService(self._repo)

            validation_result = await self._validation_service.validate_full_composition(
                agent_id=None,
                graph_schema=graph_schema,
                sub_agent_ids=sub_agent_ids,
            )
            if not validation_result.valid:
                raise ValueError(
                    f"Composition validation failed: {'; '.join(validation_result.errors)}"
                )

        existing = await self._repo.get_by_name(name)
        if existing:
            raise ValueError(f"Agent definition with name '{name}' already exists")

        return await self._repo.create(
            name=name,
            persona_id=persona_id,
            agent_type="dynamic",
            description=description,
            graph_schema=graph_schema,
            brain_type=brain_type,
            memory_type=memory_type,
            system_prompt=system_prompt,
            model=model,
            mcp_tools=mcp_tools,
            mcp_tool_configs=mcp_tool_configs,
            rag_config=rag_config,
            sub_agents=sub_agents,
            sub_agent_ids=sub_agent_ids,
            supervisor_prompt=supervisor_prompt,
            stages=stages,
            pipeline_prompt=pipeline_prompt,
            reflection_prompt=reflection_prompt,
            max_iterations=max_iterations,
            tags=tags,
        )

    async def get_agent_definition(self, id: UUID):
        return await self._repo.get_by_id(id)

    async def get_agent_definition_by_persona_id(self, persona_id: int):
        return await self._repo.get_by_persona_id(persona_id)

    async def get_agent_definition_by_name(self, name: str):
        return await self._repo.get_by_name(name)

    async def list_agent_definitions(
        self,
        graph_schema: str | None = None,
        active_only: bool = True,
    ) -> list:
        return await self._repo.list_all(graph_schema=graph_schema, active_only=active_only)

    async def update_agent_definition(
        self,
        id: UUID,
        updates: dict[str, Any],
    ):
        graph_schema = updates.get("graph_schema")
        normalized_graph_schema = (
            self._normalize_graph_schema(
                graph_schema or "zero_shot",
                updates.get("mcp_tools"),
                updates.get("rag_config"),
            )
            if graph_schema
            or updates.get("mcp_tools") is not None
            or updates.get("rag_config") is not None
            else None
        )

        if normalized_graph_schema:
            updates["graph_schema"] = normalized_graph_schema
            graph_schema = normalized_graph_schema

        if graph_schema:
            from agents.graphs.schemas import get_schema

            schema = get_schema(graph_schema)
            if not schema:
                raise ValueError(f"Invalid graph schema: {graph_schema}")

            sub_agents = updates.get("sub_agents", [])
            if sub_agents and not schema.supports_sub_agents:
                raise ValueError(f"Schema '{graph_schema}' does not support sub-agents")

            mcp_tools = updates.get("mcp_tools", [])
            if mcp_tools and not schema.supports_tools:
                raise ValueError(f"Schema '{graph_schema}' does not support tools")

        # NEW: Validate sub-agent references if updating
        if "sub_agent_ids" in updates:
            new_sub_agent_ids = updates.get("sub_agent_ids", [])

            if not self._validation_service:
                self._validation_service = CompositionValidationService(self._repo)

            validation_result = await self._validation_service.validate_full_composition(
                agent_id=id,
                graph_schema=graph_schema or "zero_shot",
                sub_agent_ids=new_sub_agent_ids,
            )

            if not validation_result.valid:
                raise ValueError(
                    f"Composition validation failed: {'; '.join(validation_result.errors)}"
                )

            # Increment version for cache validation
            agent = await self._repo.get_by_id(id)
            if agent:
                updates["sub_agent_config_version"] = agent.sub_agent_config_version + 1

        # Invalidate cache for this definition so next request reloads
        from agents.dynamic_agent import invalidate_agent_cache

        invalidate_agent_cache(str(id))

        # NEW: Also cascade invalidate if dependents need recompilation
        if "sub_agent_ids" in updates and not self._cache_service:
            self._cache_service = CacheInvalidationService(self._repo)

        if self._cache_service:
            await self._cache_service.invalidate_agent_and_dependents(id)

        return await self._repo.update(id, updates)

    async def delete_agent_definition(self, id: UUID) -> bool:
        from agents.dynamic_agent import invalidate_agent_cache

        invalidate_agent_cache(str(id))
        return await self._repo.delete(id)

    async def activate_agent_definition(self, id: UUID) -> bool:
        return await self._repo.activate(id)

    async def deactivate_agent_definition(self, id: UUID) -> bool:
        return await self._repo.deactivate(id)

    # ==================== Composition Management Methods ====================
    # New methods for managing sub-agent references and composition hierarchies

    async def create_with_sub_agents(
        self,
        name: str,
        graph_schema: str,
        sub_agent_ids: list[UUID] | None = None,
        **kwargs,
    ):
        """
        Create agent with sub-agent references.

        Validates composition before saving:
        1. All sub-agents exist and are active
        2. No circular dependencies
        3. Schema compatibility
        4. Max depth <= 5

        Args:
            name: Agent name
            graph_schema: Graph schema type
            sub_agent_ids: List of referenced agent IDs
            **kwargs: Other agent fields

        Returns:
            Created AgentDefinitionModel

        Raises:
            CompositionValidationError: If validation fails
        """
        # Get or create validation service
        if not self._validation_service:
            self._validation_service = CompositionValidationService(self._repo)

        # Validate composition
        sub_ids = sub_agent_ids or []
        validation_result = await self._validation_service.validate_full_composition(
            agent_id=None,  # Creating new
            graph_schema=graph_schema,
            sub_agent_ids=sub_ids,
        )

        if not validation_result.valid:
            raise ValueError(
                f"Composition validation failed: {'; '.join(validation_result.errors)}"
            )

        # Create agent with sub_agent_ids
        return await self._repo.create(
            name=name,
            graph_schema=graph_schema,
            sub_agent_ids=sub_ids,
            **kwargs,
        )

    async def update_sub_agents(
        self,
        agent_id: UUID,
        new_sub_agent_ids: list[UUID],
    ):
        """
        Update agent's sub-agents and cascade invalidate cache.

        Args:
            agent_id: Agent to update
            new_sub_agent_ids: New list of referenced agent IDs

        Returns:
            Updated AgentDefinitionModel

        Raises:
            CompositionValidationError: If validation fails
        """
        # Load agent
        agent = await self._repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Get or create validation service
        if not self._validation_service:
            self._validation_service = CompositionValidationService(self._repo)

        # Validate new composition
        validation_result = await self._validation_service.validate_full_composition(
            agent_id=agent_id,
            graph_schema=agent.graph_schema,
            sub_agent_ids=new_sub_agent_ids,
        )

        if not validation_result.valid:
            raise ValueError(
                f"Composition validation failed: {'; '.join(validation_result.errors)}"
            )

        # Update DB
        updates = {
            "sub_agent_ids": new_sub_agent_ids,
            "sub_agent_config_version": agent.sub_agent_config_version + 1,
        }
        updated = await self._repo.update(agent_id, updates)

        # Cascade invalidate cache
        if not self._cache_service:
            self._cache_service = CacheInvalidationService(self._repo)

        await self._cache_service.invalidate_agent_and_dependents(agent_id)

        logger.info(
            f"Updated agent {agent_id} sub-agents: "
            f"{len(new_sub_agent_ids)} references, "
            f"invalidated all dependents"
        )

        return updated

    async def get_sub_agents(self, agent_id: UUID) -> list:
        """
        Load all sub-agents for an agent.

        Returns:
            List of AgentDefinitionModel for all referenced sub-agents
        """
        agent = await self._repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.sub_agent_ids:
            return []

        sub_agents = []
        for sub_id in agent.sub_agent_ids:
            sub_agent = await self._repo.get_by_id(sub_id)
            if sub_agent:
                sub_agents.append(sub_agent)

        return sub_agents

    async def get_composition_info(self, agent_id: UUID) -> dict[str, Any]:
        """
        Get hierarchical composition structure for UI preview.

        Returns:
            {
                "id": str,
                "name": str,
                "graph_schema": str,
                "depth": int,
                "sub_agents": [
                    {same structure recursively}
                ]
            }
        """
        agent = await self._repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        async def build_tree(agent_def) -> dict[str, Any]:
            sub_agents_list = await self.get_sub_agents(agent_def.id)

            # Get depth
            if not self._validation_service:
                self._validation_service = CompositionValidationService(self._repo)

            depth = await self._validation_service.get_composition_depth_async(agent_def.id)

            return {
                "id": str(agent_def.id),
                "name": agent_def.name,
                "graph_schema": agent_def.graph_schema,
                "status": "active" if agent_def.is_active else "inactive",
                "depth": depth,
                "sub_agents": [await build_tree(sub) for sub in sub_agents_list],
            }

        return await build_tree(agent)

    async def find_agents_by_sub_agent_id(self, sub_agent_id: UUID) -> list[UUID]:
        """
        Find all agents that reference this agent as a sub-agent.

        Returns:
            List of agent UUIDs
        """
        return await self._repo.find_agents_by_sub_agent_id(sub_agent_id)

    async def validate_composition(
        self,
        agent_id: UUID | None,
        graph_schema: str,
        sub_agent_ids: list[UUID],
    ) -> dict[str, Any]:
        """
        Validate composition without saving.

        Args:
            agent_id: None if creating, set if updating
            graph_schema: Master agent schema
            sub_agent_ids: Proposed sub-agent IDs

        Returns:
            {
                "valid": bool,
                "errors": [str],
                "warnings": [str],
                "depth": int
            }
        """
        if not self._validation_service:
            self._validation_service = CompositionValidationService(self._repo)

        result = await self._validation_service.validate_full_composition(
            agent_id, graph_schema, sub_agent_ids
        )

        return {
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "depth": result.depth,
        }


class GraphSchemaService:
    """Returns information about available graph schemas for frontend consumption."""

    @staticmethod
    def get_available_schemas() -> list[dict[str, Any]]:
        from agents.graphs.schemas import get_all_schemas

        schemas = get_all_schemas()
        return [
            {
                "schema_type": s.schema_type.value,
                "description": s.description,
                "supports_memory": s.supports_memory,
                "supports_tools": s.supports_tools,
                "supports_rag": s.supports_rag,
                "supports_sub_agents": s.supports_sub_agents,
                "is_multi_step": s.is_multi_step,
                "config_schema": s.config_schema,
                "required_fields": s.required_fields,
            }
            for s in schemas
        ]

    @staticmethod
    def get_schema_info(schema_type: str) -> dict[str, Any] | None:
        from agents.graphs.schemas import get_schema

        schema = get_schema(schema_type)
        if not schema:
            return None
        return {
            "schema_type": schema.schema_type.value,
            "description": schema.description,
            "supports_memory": schema.supports_memory,
            "supports_tools": schema.supports_tools,
            "supports_rag": schema.supports_rag,
            "supports_sub_agents": schema.supports_sub_agents,
            "is_multi_step": schema.is_multi_step,
            "config_schema": schema.config_schema,
            "required_fields": schema.required_fields,
        }


class BrainTypeService:
    BRAIN_TYPES = [
        {"brain_type": "llm", "description": "Standard LLM brain - direct model calls"},
        {"brain_type": "guard", "description": "Safety brain with input/output filtering"},
        {
            "brain_type": "multi_model",
            "description": "Multi-model brain - routes to different models",
        },
    ]

    @staticmethod
    def get_available_brain_types() -> list[dict[str, Any]]:
        return BrainTypeService.BRAIN_TYPES


class MemoryTypeService:
    MEMORY_TYPES = [
        {"memory_type": "none", "description": "No memory - stateless agent"},
        {"memory_type": "long_term", "description": "Long-term memory using LangGraph BaseStore"},
        {"memory_type": "buffer", "description": "Buffer memory - recent k messages"},
    ]

    @staticmethod
    def get_available_memory_types() -> list[dict[str, Any]]:
        return MemoryTypeService.MEMORY_TYPES
