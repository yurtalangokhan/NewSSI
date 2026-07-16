"""Agent domain service - handles agent registry, definitions, and management."""

import logging
from typing import Any
from uuid import UUID

from models.agents import AgentInfo

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
    """

    def __init__(self, repository):
        self._repo = repository

    @staticmethod
    def _normalize_graph_schema(
        graph_schema: str,
        mcp_tools: list[str] | None = None,
        rag_config: dict[str, Any] | None = None,
    ) -> str:
        has_rag_tools = any((rag_config or {}).get(key) for key in ("document_processing", "knowledge_graph", "collections"))
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
        rag_config: dict[str, Any] | None = None,
        sub_agents: list[dict[str, Any]] | None = None,
        supervisor_prompt: str | None = None,
        stages: list[dict[str, Any]] | None = None,
        pipeline_prompt: str | None = None,
        reflection_prompt: str | None = None,
        max_iterations: int = 3,
        description: str | None = None,
        tags: list[str] | None = None,
    ):
        from agents.graphs.schemas import get_schema

        graph_schema = self._normalize_graph_schema(graph_schema, mcp_tools, rag_config)

        schema = get_schema(graph_schema)
        if not schema:
            raise ValueError(f"Invalid graph schema: {graph_schema}")

        if sub_agents and not schema.supports_sub_agents:
            raise ValueError(f"Schema '{graph_schema}' does not support sub-agents")

        if mcp_tools and not schema.supports_tools:
            raise ValueError(f"Schema '{graph_schema}' does not support tools")

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
            rag_config=rag_config,
            sub_agents=sub_agents,
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
        normalized_graph_schema = self._normalize_graph_schema(
            graph_schema or "zero_shot",
            updates.get("mcp_tools"),
            updates.get("rag_config"),
        ) if graph_schema or updates.get("mcp_tools") is not None or updates.get("rag_config") is not None else None

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

        # Invalidate cache for this definition so next request reloads
        from agents.dynamic_agent import invalidate_agent_cache

        invalidate_agent_cache(str(id))

        return await self._repo.update(id, updates)

    async def delete_agent_definition(self, id: UUID) -> bool:
        from agents.dynamic_agent import invalidate_agent_cache

        invalidate_agent_cache(str(id))
        return await self._repo.delete(id)

    async def activate_agent_definition(self, id: UUID) -> bool:
        return await self._repo.activate(id)

    async def deactivate_agent_definition(self, id: UUID) -> bool:
        return await self._repo.deactivate(id)


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
        {"brain_type": "multi_model", "description": "Multi-model brain - routes to different models"},
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
