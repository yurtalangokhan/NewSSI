"""Assistant Agent Service - Singleton service for managing assistants and agents."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.db.repositories import AssistantRepository
from core.logger import get_logger

logger = get_logger(__name__)


class AssistantAgentService:
    """
    Singleton service for managing assistants and agent instances.

    Provides:
    - Assistant CRUD operations (stored in database)
    - Agent listing and retrieval (from agents module)
    - Configured agent creation with runtime configuration
    """

    _instance: "AssistantAgentService | None" = None
    _initialized: bool = False

    def __init__(self):
        if AssistantAgentService._instance is not None:
            raise RuntimeError("Use get_instance() to get singleton")
        self._assistant_repo = AssistantRepository()

    @classmethod
    def get_instance(cls) -> "AssistantAgentService":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================================
    # Assistant CRUD (stored in database)
    # =========================================================================

    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None:
        """Get an assistant by ID from the database."""
        return await self._assistant_repo.get_assistant(assistant_id)

    async def list_assistants(self) -> list[dict[str, Any]]:
        """List all assistants from the database."""
        return await self._assistant_repo.list_assistants()

    async def create_assistant(
        self,
        graph_id: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new assistant in the database."""
        assistant_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        assistant = {
            "assistant_id": assistant_id,
            "graph_id": graph_id,
            "name": name or f"{graph_id}-{assistant_id[:8]}",
            "config": config or {},
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }

        return await self._assistant_repo.save_assistant(assistant)

    async def update_assistant(
        self,
        assistant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an assistant in the database."""
        if "updated_at" not in updates:
            updates["updated_at"] = datetime.now(UTC).isoformat()
        return await self._assistant_repo.update_assistant(assistant_id, updates)

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant from the database."""
        return await self._assistant_repo.delete_assistant(assistant_id)

    # =========================================================================
    # Agent listing and retrieval (from agents module)
    # =========================================================================

    def list_agents(self) -> list[dict[str, Any]]:
        """List all available agents from the agents module."""
        from agents import get_all_agent_info

        agents = get_all_agent_info()
        return [{"key": agent.key, "description": agent.description} for agent in agents]

    def get_agent_info(self, agent_id: str) -> dict[str, Any] | None:
        """Get info for a specific agent."""
        from agents import get_all_agent_info

        agents = get_all_agent_info()
        for agent in agents:
            if agent.key == agent_id:
                return {"key": agent.key, "description": agent.description}
        return None

    def get_default_agent_id(self) -> str:
        """Get the default agent ID."""
        from agents import DEFAULT_AGENT

        return DEFAULT_AGENT

    # =========================================================================
    # Graph/config resolution (for agent execution)
    # =========================================================================

    async def get_graph_and_config(self, agent_id: str) -> tuple[str, dict[str, Any]]:
        """
        Resolve agent ID to graph ID and config.

        Handles:
        - Direct agent ID (e.g., "chatbot", "configurable-mcp-agent")
        - Persona ID (numeric string) - loads base_agent and mcp_tools from persona
        - Assistant ID (UUID) - loads from assistant table

        Returns:
            Tuple of (graph_id, config)
        """
        config: dict = {}
        graph_id = agent_id

        # Check if agent_id is an AgentDefinition UUID.
        # For dynamic agents we must expose runtime-relevant config (especially
        # rag_config) so tools receive it via RunnableConfig.configurable.
        try:
            from uuid import UUID as _UUID

            definition_uuid = _UUID(agent_id)
            definition = await self._get_agent_definition(definition_uuid)
            if definition:
                graph_id = agent_id
                definition_cfg = definition.to_config() or {}

                runtime_cfg: dict[str, Any] = {}
                if definition_cfg.get("model"):
                    runtime_cfg["model"] = definition_cfg["model"]
                if definition_cfg.get("system_prompt"):
                    runtime_cfg["system_prompt"] = definition_cfg["system_prompt"]
                if definition_cfg.get("mcp_tools"):
                    runtime_cfg["mcp_tools"] = definition_cfg["mcp_tools"]
                if definition_cfg.get("rag_config"):
                    runtime_cfg["rag_config"] = definition_cfg["rag_config"]
                if definition_cfg.get("memory_type"):
                    runtime_cfg["memory_type"] = definition_cfg["memory_type"]

                return graph_id, runtime_cfg
        except (ValueError, AttributeError):
            pass

        # Check if agent_id is a persona ID (numeric)
        if agent_id.isdigit():
            from service.PersonaRepository import PersonaDB

            try:
                persona = await PersonaDB.get(int(agent_id))
                if persona and not persona.get("is_builtin"):
                    # Custom persona - use base_agent, MCP tools, and RAG config
                    base_agent = persona.get("base_agent")
                    mcp_tools = persona.get("mcp_tools", [])
                    rag_config = persona.get("rag_config") or {}

                    if base_agent == "dynamic-agent":
                        from agents.storage.repository import AgentDefinitionRepository

                        definition = await AgentDefinitionRepository().get_by_persona_id(
                            int(agent_id)
                        )
                        if definition:
                            definition_cfg = definition.to_config() or {}
                            runtime_cfg: dict[str, Any] = {}
                            for key in (
                                "model",
                                "system_prompt",
                                "mcp_tools",
                                "rag_config",
                                "memory_type",
                            ):
                                if definition_cfg.get(key):
                                    runtime_cfg[key] = definition_cfg[key]
                            return str(definition.id), runtime_cfg

                    if base_agent:
                        graph_id = base_agent

                    if mcp_tools:
                        config["mcp_tools"] = mcp_tools

                    if rag_config:
                        config["rag_config"] = rag_config

                    # Also include system_prompt from persona
                    system_prompt = persona.get("system_prompt")
                    if system_prompt:
                        config["system_prompt"] = system_prompt

                    logger.info(
                        f"Loaded persona config: base_agent={graph_id}, mcp_tools={mcp_tools}, rag_config_keys={list(rag_config.keys())}"
                    )
                    return graph_id, config
            except Exception as e:
                logger.warning(f"Could not load persona {agent_id}: {e}")

        # Check for assistant in database
        try:
            stored = await self.get_assistant(agent_id)
            if stored:
                graph_id = stored.get("graph_id", agent_id)
                config = stored.get("config", {})
                return graph_id, config
        except Exception as e:
            logger.warning("Could not load stored assistant %s: %s", agent_id, e)

        return graph_id, config

    async def get_configured_agent(
        self,
        agent_id: str,
        agent_config: dict[str, Any] | None = None,
    ):
        """
        Get agent with dynamic configuration applied.

        Resolution order:
        1. If agent_id looks like a UUID → look up AgentDefinition in DB → return DynamicAgent
        2. If agent_id is numeric → resolve persona → fall through to registry
        3. Look up in agents registry (chatbot, configurable-mcp-agent, …)

        Args:
            agent_id: Agent/graph/persona/definition ID
            agent_config: Runtime config overrides

        Returns:
            Configured agent graph or LazyLoadingAgent
        """
        from agents.agents import agents
        from agents.lazy_agent import LazyLoadingAgent

        graph_id, stored_config = await self.get_graph_and_config(agent_id)
        merged_config = {**stored_config, **(agent_config or {})}

        # ------------------------------------------------------------------
        # 1.  UUID → AgentDefinition (DynamicAgent). This can be the original
        # agent_id for legacy direct calls, or graph_id resolved from a persona.
        # ------------------------------------------------------------------
        try:
            from uuid import UUID as _UUID

            definition_uuid = _UUID(graph_id)
            definition = await self._get_agent_definition(definition_uuid)
            if definition:
                return await self._get_or_create_dynamic_agent(definition)
        except (ValueError, AttributeError):
            pass  # not a UUID string, continue to registry lookup

        # ------------------------------------------------------------------
        # 2 & 3.  Legacy registry lookup (personas + static agents)
        # ------------------------------------------------------------------
        agent_entry = agents.get(graph_id)
        if not agent_entry:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Agent {graph_id} not found")

        graph_like = agent_entry.graph_like

        # Ensure checkpointer is set on the agent/graph
        from service.CheckpointerService import get_checkpointer

        checkpointer = get_checkpointer()

        # Set checkpointer on LazyLoadingAgent instances
        if isinstance(graph_like, LazyLoadingAgent) and checkpointer:
            if not hasattr(graph_like, "checkpointer") or not graph_like.checkpointer:
                graph_like._checkpointer = checkpointer

        if isinstance(graph_like, LazyLoadingAgent):
            if hasattr(graph_like, "create_configured_graph") and "sub_agents" in merged_config:
                sub_agents_config = merged_config.get("sub_agents", [])
                supervisor_prompt = merged_config.get("supervisor_prompt")
                model_name = merged_config.get("model")

                if (
                    sub_agents_config
                    and isinstance(sub_agents_config, list)
                    and len(sub_agents_config) > 0
                ):
                    if isinstance(sub_agents_config[0], dict):
                        return graph_like.create_configured_graph(
                            sub_agents_config,
                            supervisor_prompt=supervisor_prompt,
                            model_name=model_name,
                        )

            if (
                hasattr(graph_like, "create_configured_graph")
                and "pipeline_stages" in merged_config
            ):
                pipeline_stages = merged_config.get("pipeline_stages", [])
                model_name = merged_config.get("model")
                retry_count = merged_config.get("retry_count", 2)
                on_error = merged_config.get("on_error", "abort")

                if pipeline_stages:
                    return graph_like.create_configured_graph(
                        pipeline_stages,
                        model_name=model_name,
                        retry_count=retry_count,
                        on_error=on_error,
                    )

            # Handle mcp_tools for custom agents (configurable-mcp-agent pattern)
            if hasattr(graph_like, "create_configured_graph") and "mcp_tools" in merged_config:
                mcp_tools = merged_config.get("mcp_tools", [])
                system_prompt = merged_config.get("system_prompt")
                model_name = merged_config.get("model")

                if mcp_tools or system_prompt:
                    return graph_like.create_configured_graph(
                        mcp_tools=mcp_tools,
                        system_prompt=system_prompt,
                        model_name=model_name,
                    )

            return graph_like

        # For non-lazy agents, ensure checkpointer is set
        if checkpointer and hasattr(graph_like, "checkpointer"):
            graph_like.checkpointer = checkpointer

        return graph_like

    # =========================================================================
    # Dynamic agent helpers
    # =========================================================================

    async def _get_agent_definition(self, definition_id):
        """Fetch AgentDefinitionModel from DB by UUID."""
        try:
            from agents.storage.repository import AgentDefinitionRepository

            repo = AgentDefinitionRepository()
            return await repo.get_by_id(definition_id)
        except Exception as e:
            logger.warning("Could not load agent definition %s: %s", definition_id, e)
            return None

    async def _get_or_create_dynamic_agent(self, definition):
        """
        Return a loaded DynamicAgent for the given definition.

        Uses a per-definition cache so MCP tools are only loaded once.
        Cache is invalidated on definition update/delete via AgentDefinitionService.
        """
        from agents.dynamic_agent import (
            DynamicAgent,
            cache_agent,
            get_cached_agent,
        )
        from service.CheckpointerService import get_checkpointer

        definition_id = str(definition.id)
        checkpointer = get_checkpointer()
        cached = get_cached_agent(definition_id)
        if cached is not None:
            # If an older cached graph was built without persistence, recreate it.
            try:
                cached_graph = cached.get_graph()
                cached_checkpointer = getattr(cached_graph, "checkpointer", None)
            except Exception:
                cached_checkpointer = None

            cached_load_failed = bool(getattr(cached, "_load_failed", False))

            if cached_load_failed:
                logger.warning(
                    "Recreating DynamicAgent '%s' (id=%s) because previous load fell back",
                    getattr(definition, "name", definition_id),
                    definition_id,
                )
            elif checkpointer is not None and cached_checkpointer is None:
                logger.warning(
                    "Recreating DynamicAgent '%s' (id=%s) because cached graph has no checkpointer",
                    getattr(definition, "name", definition_id),
                    definition_id,
                )
            else:
                return cached

        config = definition.to_config()
        agent = DynamicAgent(agent_config=config)

        if checkpointer:
            agent._checkpointer = checkpointer

        await agent.load()
        cache_agent(definition_id, agent)
        logger.info("DynamicAgent '%s' created and cached (id=%s)", definition.name, definition_id)
        return agent


# Singleton instance accessor
assistant_agent_service = AssistantAgentService.get_instance()
