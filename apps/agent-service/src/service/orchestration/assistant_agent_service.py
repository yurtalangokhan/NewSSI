"""Assistant Agent Service - Singleton service for managing assistants and agents."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from error_contract.agent import AgentPermissionError as AgentPermissionError

from core.exceptions import NotFoundError
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import agent_definition_repository, persona_repository
from service.chat.chat_agent_resolver import resolve_custom_persona_agent
from service.runtime import store_service as StoreService

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
        return await StoreService.get_assistant_from_store(assistant_id)

    async def list_assistants(self) -> list[dict[str, Any]]:
        """List all assistants from the database."""
        return await StoreService.list_assistants_from_store()

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

        return await StoreService.save_assistant_async(assistant)

    async def update_assistant(
        self,
        assistant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update an assistant in the database."""
        if "updated_at" not in updates:
            updates["updated_at"] = datetime.now(UTC).isoformat()
        return await StoreService.update_assistant_in_store(assistant_id, updates)

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant from the database."""
        return await StoreService.delete_assistant_from_store(assistant_id)

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

    async def get_graph_and_config(self, agent_id: str | int) -> tuple[str, dict[str, Any]]:
        """
        Resolve agent ID to graph ID and config.

        Handles:
        - Direct agent ID (e.g., "chatbot", "configurable-mcp-agent")
        - Persona ID (numeric string) - loads base_agent and mcp_tools from persona
        - Assistant ID (UUID) - loads from assistant table

        Returns:
            Tuple of (graph_id, config)
        """
        agent_id = str(agent_id)
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
                if definition_cfg.get("mcp_tool_configs"):
                    runtime_cfg["mcp_tool_configs"] = definition_cfg["mcp_tool_configs"]
                if definition_cfg.get("rag_config"):
                    runtime_cfg["rag_config"] = definition_cfg["rag_config"]
                if definition_cfg.get("memory_type"):
                    runtime_cfg["memory_type"] = definition_cfg["memory_type"]

                return graph_id, runtime_cfg
        except (ValueError, AttributeError):
            pass

        # Check if agent_id is a persona ID (numeric)
        if agent_id.isdigit():
            try:
                persona = await persona_repository().get(int(agent_id))
                if persona and not persona.get("is_builtin"):
                    # Custom persona: the same mapping the chat path uses, so a
                    # run by persona id gets the persona's prompt, tools, RAG
                    # config and connector bindings.
                    _, persona_config = resolve_custom_persona_agent(int(agent_id), persona, None)

                    if persona.get("base_agent") == "dynamic-agent":
                        definition = await agent_definition_repository().get_by_persona_id(int(agent_id))
                        if definition:
                            definition_cfg = definition.to_config() or {}
                            runtime_cfg: dict[str, Any] = {}
                            if persona.get("user_id"):
                                runtime_cfg["owner_user_id"] = str(persona["user_id"])
                            for key in (
                                "model",
                                "system_prompt",
                                "mcp_tools",
                                "mcp_tool_configs",
                                "rag_config",
                                "memory_type",
                            ):
                                if definition_cfg.get(key):
                                    runtime_cfg[key] = definition_cfg[key]
                            return str(definition.id), {**runtime_cfg, **persona_config}

                    if persona.get("base_agent"):
                        graph_id = persona["base_agent"]

                    logger.info(
                        "Loaded persona config: base_agent=%s, mcp_tools=%s, rag_config_keys=%s",
                        graph_id,
                        persona_config.get("mcp_tools", []),
                        list(persona_config.get("rag_config", {})),
                    )
                    return graph_id, persona_config
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
        agent_id: str | int,
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
        from agents.primitives.base import LazyLoadingAgent
        from agents.registry.registry import agents

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
            from localization import t

            raise NotFoundError(
                code="agent.not_found",
                message=t("agent.not_found", agent_id=graph_id),
                details={"agent_id": graph_id},
            )

        graph_like = agent_entry.graph_like

        # Ensure checkpointer is set on the agent/graph
        from infrastructure.runtime.checkpointer import get_checkpointer

        checkpointer = get_checkpointer()

        # Set checkpointer on LazyLoadingAgent instances
        if (
            isinstance(graph_like, LazyLoadingAgent)
            and checkpointer
            and (not hasattr(graph_like, "checkpointer") or not graph_like.checkpointer)
        ):
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
                    and isinstance(sub_agents_config[0], dict)
                ):
                    return graph_like.create_configured_graph(
                        sub_agents_config,
                        supervisor_prompt=supervisor_prompt,
                        model_name=model_name,
                    )

            if hasattr(graph_like, "create_configured_graph") and "pipeline_stages" in merged_config:
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
            repo = agent_definition_repository()
            return await repo.get_by_id(definition_id)
        except Exception as e:
            logger.warning("Could not load agent definition %s: %s", definition_id, e)
            return None

    async def _get_or_create_dynamic_agent(self, definition):
        """
        Return a loaded agent (DynamicAgent or FlowAgent) for the given
        definition — the class depends on definition.graph_schema, decided
        once by agents/agent_factory.py.

        Uses a per-definition cache so MCP tools/flow graphs are only loaded
        once. Cache is invalidated on definition update/delete via
        AgentDefinitionService. Flow-backed and classic definitions keep
        separate caches (agents/flow_agent.py vs agents/dynamic_agent.py).
        """
        from infrastructure.runtime.checkpointer import get_checkpointer

        is_flow = getattr(definition, "graph_schema", None) == "flow"
        if is_flow:
            from agents.implementations.flow_agent import cache_agent, get_cached_agent
        else:
            from agents.implementations.dynamic_agent import cache_agent, get_cached_agent

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

            if checkpointer is not None and cached_checkpointer is None:
                logger.warning(
                    "Recreating agent '%s' (id=%s) because cached graph has no checkpointer",
                    getattr(definition, "name", definition_id),
                    definition_id,
                )
            else:
                return cached

        from agents.registry.agent_factory import create_agent_for_definition

        agent = await create_agent_for_definition(definition, checkpointer=checkpointer)

        # A classic definition comes back already loaded — AgentFactory loads
        # it while composing the runtime. Only a FlowAgent still needs it;
        # loading a DynamicAgent twice would re-resolve its tools and rebuild
        # the graph for nothing.
        if is_flow:
            await agent.load()
        await cache_agent(definition_id, agent)
        logger.info(
            "%s '%s' created and cached (id=%s)",
            "FlowAgent" if is_flow else "DynamicAgent",
            definition.name,
            definition_id,
        )
        return agent


# Singleton instance accessor
assistant_agent_service = AssistantAgentService.get_instance()

# Singleton instance
_assistant_agent_service: AssistantAgentService | None = None


def get_assistant_agent_service() -> AssistantAgentService:
    """Get the singleton AssistantAgentService instance."""
    global _assistant_agent_service
    if _assistant_agent_service is None:
        _assistant_agent_service = AssistantAgentService.get_instance()
    return _assistant_agent_service
