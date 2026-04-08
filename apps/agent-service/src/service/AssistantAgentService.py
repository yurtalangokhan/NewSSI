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
        from schema import AgentInfo

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

        # Check if agent_id is a persona ID (numeric)
        if agent_id.isdigit():
            from service.PersonaRepository import PersonaDB

            try:
                persona = await PersonaDB.get(int(agent_id))
                if persona and not persona.get("is_builtin"):
                    # Custom persona - use base_agent and mcp_tools
                    base_agent = persona.get("base_agent")
                    mcp_tools = persona.get("mcp_tools", [])

                    if base_agent:
                        graph_id = base_agent

                    if mcp_tools:
                        config["mcp_tools"] = mcp_tools

                    # Also include system_prompt from persona
                    system_prompt = persona.get("system_prompt")
                    if system_prompt:
                        config["system_prompt"] = system_prompt

                    logger.info(
                        f"Loaded persona config: base_agent={graph_id}, mcp_tools={mcp_tools}"
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

        For supervisor agents, creates a configured graph based on the config.

        Args:
            agent_id: The base agent/graph ID
            agent_config: Configuration including sub_agents or pipeline_stages

        Returns:
            Configured agent graph
        """
        from agents.agents import agents
        from agents.lazy_agent import LazyLoadingAgent

        graph_id, stored_config = await self.get_graph_and_config(agent_id)
        merged_config = {**stored_config, **(agent_config or {})}

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

            graph = graph_like.get_graph()
            # Set checkpointer on the compiled graph
            if checkpointer:
                graph.checkpointer = checkpointer
            return graph

        # For non-lazy agents, ensure checkpointer is set
        if checkpointer and hasattr(graph_like, "checkpointer"):
            graph_like.checkpointer = checkpointer

        return graph_like


# Singleton instance accessor
assistant_agent_service = AssistantAgentService.get_instance()
