"""
Dynamic Flat Supervisor Agent.
Manages multiple sub-agents in parallel based on runtime configuration.
Each sub-agent is defined with a name, system prompt, and MCP tools.
"""

import os
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel
from langgraph_supervisor import create_supervisor

from agents.lazy_agent import LazyLoadingAgent
from core import get_model, settings
from core.logger import get_logger
from memory.long_term import build_event_emitters

logger = get_logger(__name__)

# Default supervisor prompt
DEFAULT_SUPERVISOR_PROMPT = """You are a team supervisor managing multiple specialized agents.
Your job is to analyze each user request and delegate to the most appropriate agent based on their capabilities.

IMPORTANT RULES:
1. Always delegate tasks to the appropriate specialized agent - do NOT answer directly yourself.
2. If the user provides a URL or asks about web content, delegate to an agent with fetch_webpage tool.
3. If the user asks for fact-checking or verification, delegate to an agent with web_search tool.
4. After receiving results from agents, synthesize the information and provide a coherent response.
5. You can delegate to multiple agents if the task requires different expertise."""

# Default sub-agents configuration
DEFAULT_SUB_AGENTS = [
    {
        "name": "assistant",
        "system_prompt": "You are a helpful assistant. Answer questions and help with tasks.",
        "mcp_tools": [],
    }
]


class DynamicFlatSupervisor(LazyLoadingAgent):
    """
    A dynamic flat supervisor that manages multiple named sub-agents.

    Configuration (via agent_config):
        - supervisor_prompt: Custom system prompt for the supervisor
        - sub_agents: List of sub-agent definitions, each with:
            - name: Agent identifier
            - system_prompt: Instructions for this agent
            - mcp_tools: List of MCP tool names this agent can use
    """

    def __init__(self) -> None:
        super().__init__()
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_tools: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "langgraph-supervisor-agent"

    @property
    def description(self) -> str:
        return "A dynamic supervisor that coordinates multiple agents working in parallel"

    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return

        try:
            # Try to load MCP tools
            await self._load_mcp_tools()

            # Create default graph
            self._default_graph = self._create_supervisor_graph(DEFAULT_SUB_AGENTS)
            self._graph = self._default_graph
            self._loaded = True

            logger.info(
                f"Dynamic Flat Supervisor initialized with {len(self._mcp_tools)} MCP tools available"
            )

        except Exception:
            logger.error("error")
            # Create a minimal fallback graph
            self._default_graph = self._create_fallback_graph()
            self._graph = self._default_graph
            self._loaded = True
            logger.warning("Using fallback graph without MCP tools")

    async def _load_mcp_tools(self) -> None:
        """Load tools from MCP server."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            mcp_url = os.environ.get("MCP_SERVER_URL", "http://tools-service:8003/mcp")
            token = (os.environ.get("INTERNAL_SERVICE_TOKEN") or "").strip()
            headers = {"Authorization": f"Bearer {token}"} if token else None

            client = MultiServerMCPClient(
                connections={
                    "mcp-tools": {
                        "transport": "streamable_http",
                        "url": mcp_url,
                        **({"headers": headers} if headers else {}),
                    }
                }
            )

            # New API: directly call get_tools() without context manager
            tools = await client.get_tools()

            # Store tools by name for easy lookup
            for tool in tools:
                self._mcp_tools[tool.name] = tool

            logger.info(
                f"Loaded {len(tools)} MCP tools for flat supervisor: {list(self._mcp_tools.keys())}"
            )

        except Exception as e:
            logger.warning("Failed to load MCP tools: %s", e)

    def _create_fallback_graph(self) -> CompiledStateGraph:
        """Create a minimal fallback graph."""
        model = get_model(settings.DEFAULT_MODEL)

        agent = create_react_agent(
            model=model,
            tools=[],
            name="fallback-agent",
            prompt="You are a helpful assistant. MCP tools are not available.",
        )

        workflow = create_supervisor(
            [agent],
            model=model,
            prompt="You are a supervisor. Currently no sub-agents are configured.",
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    def _create_supervisor_graph(
        self,
        sub_agents_config: list[dict[str, Any]],
        supervisor_prompt: str | None = None,
        model_name: str | None = None,
        checkpointer: Any | None = None,
    ) -> CompiledStateGraph | Pregel:
        """
        Create a supervisor graph with the specified sub-agents.

        Args:
            sub_agents_config: List of sub-agent configurations. Each entry:
                - name: Agent identifier
                - system_prompt: Instructions for this agent
                - mcp_tools: List of MCP tool names
                - model: (Optional) Model override for this specific sub-agent.
                         If omitted or empty, the supervisor's model (model_name)
                         is used as fallback.
            supervisor_prompt: Optional custom prompt for supervisor
            model_name: Model for the supervisor itself (and default for sub-agents)
            checkpointer: Optional checkpointer for persistence

        Returns:
            Compiled supervisor graph
        """
        logger.info(
            "SUPERVISOR _create_supervisor_graph: Available MCP tools: %s",
            list(self._mcp_tools.keys()),
        )
        logger.info(
            "SUPERVISOR _create_supervisor_graph: settings.DEFAULT_MODEL = %s",
            settings.DEFAULT_MODEL,
        )

        supervisor_model_name = model_name or settings.DEFAULT_MODEL
        logger.info(
            "SUPERVISOR _create_supervisor_graph: Supervisor model = %s", supervisor_model_name
        )

        supervisor_model = get_model(supervisor_model_name)
        prompt = supervisor_prompt or DEFAULT_SUPERVISOR_PROMPT

        agents_list = []
        agent_descriptions = []

        for agent_config in sub_agents_config:
            agent_name = agent_config.get("name", "agent")
            system_prompt = agent_config.get("system_prompt", "You are a helpful assistant.")
            mcp_tool_names = agent_config.get("mcp_tools", [])

            # Per-agent model: use agent-specific model if provided, otherwise fall back to supervisor model
            agent_model_name = agent_config.get("model") or supervisor_model_name
            agent_model = get_model(agent_model_name)

            if agent_config.get("model"):
                logger.info(
                    "[SUPERVISOR] Agent '%s': using custom model '%s' (overrides supervisor model '%s')",
                    agent_name,
                    agent_model_name,
                    supervisor_model_name,
                )
            else:
                logger.info(
                    "[SUPERVISOR] Agent '%s': using supervisor model '%s' (no override)",
                    agent_name,
                    supervisor_model_name,
                )

            logger.info(
                "SUPERVISOR Creating agent '%s' with model=%s, requested tools: %s",
                agent_name,
                agent_model_name,
                mcp_tool_names,
            )

            # Collect tools for this agent
            agent_tools = []
            for tool_name in mcp_tool_names:
                if tool_name in self._mcp_tools:
                    agent_tools.append(self._mcp_tools[tool_name])
                else:
                    logger.warning("Tool '%s' not found for agent '%s'", tool_name, agent_name)

            # Enhance system prompt with tool usage instructions
            tool_names_str = ", ".join(mcp_tool_names) if mcp_tool_names else "none"
            enhanced_system_prompt = f"""{system_prompt}

CRITICAL INSTRUCTIONS:
- You have access to these tools: {tool_names_str}
- You MUST use your tools to complete tasks. DO NOT make up information or hallucinate.
- If asked about a URL or web page, you MUST use fetch_webpage to get the actual content first.
- If asked to search or verify information, you MUST use web_search to find real sources.
- Always base your responses on actual tool results, not assumptions.
- If a tool fails, report the error instead of making up information."""

            # Create the agent with its own model
            agent = create_react_agent(
                model=agent_model,
                tools=agent_tools,
                name=agent_name,
                prompt=SystemMessage(content=enhanced_system_prompt),
            )

            agents_list.append(agent)

            # Build description for supervisor (include model info if different)
            tool_list = ", ".join(mcp_tool_names) if mcp_tool_names else "no tools"
            model_info = (
                f", model: {agent_model_name}" if agent_model_name != supervisor_model_name else ""
            )
            agent_descriptions.append(
                f"- {agent_name}: {system_prompt[:100]}... (tools: {tool_list}{model_info})"
            )

        # Enhance supervisor prompt with agent list
        enhanced_prompt = f"""{prompt}

Available agents and their capabilities:
{chr(10).join(agent_descriptions)}

Analyze the user's request and delegate to the most appropriate agent(s). You can delegate to multiple agents if needed."""

        workflow = create_supervisor(
            agents_list,
            model=supervisor_model,
            prompt=enhanced_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        # Use provided checkpointer or create a MemorySaver fallback
        if checkpointer is None:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()
            logger.info(
                "SUPERVISOR Compiling graph with %s agents and MemorySaver checkpointer (fallback)",
                len(agents_list),
            )
        else:
            logger.info(
                "SUPERVISOR Compiling graph with {len(agents_list)} agents and provided checkpointer: {type(checkpointer).__name__}"
            )

        return workflow.compile(checkpointer=checkpointer)

    def get_graph(self) -> CompiledStateGraph | Pregel:
        """Return the default graph."""
        if not self._loaded:
            raise RuntimeError("Agent not loaded. Call load() first.")
        return self._graph

    def create_configured_graph(
        self,
        sub_agents_config: list[dict[str, Any]],
        supervisor_prompt: str | None = None,
        model_name: str | None = None,
    ) -> CompiledStateGraph | Pregel:
        """
        Create a supervisor graph with the specified sub-agents.

        Args:
            sub_agents_config: List of sub-agent configurations, each with:
                - name: Agent identifier
                - system_prompt: Instructions for this agent
                - mcp_tools: List of MCP tool names
            supervisor_prompt: Optional custom prompt for supervisor
            model_name: Optional model override

        Returns:
            Compiled supervisor graph
        """
        if not sub_agents_config:
            logger.warning("No sub-agents provided, returning default graph")
            return self._default_graph

        return self._create_supervisor_graph(
            sub_agents_config, supervisor_prompt=supervisor_prompt, model_name=model_name
        )

    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded."""
        if not self._loaded:
            await self.load()

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs: Any) -> Any:
        """
        Async invoke with dynamic configuration support.
        Creates a custom graph based on runtime configuration.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        # Get configuration
        configurable = (config or {}).get("configurable", {})

        supervisor_prompt = configurable.get("supervisor_prompt")
        sub_agents_config = configurable.get("sub_agents", [])
        model_name = configurable.get("model")

        # If custom sub-agents provided, create a custom graph
        if sub_agents_config:
            graph = self._create_supervisor_graph(
                sub_agents_config=sub_agents_config,
                supervisor_prompt=supervisor_prompt,
                model_name=model_name,
            )
            result = await graph.ainvoke(input, config=config, **kwargs)
        else:
            result = await self._graph.ainvoke(input, config=config, **kwargs)

        # Save memories from output
        configurable = (config or {}).get("configurable", {})
        _, on_save = build_event_emitters(configurable)
        await self._save_memory_from_output(result, original_messages, memories, user_id, config, on_save=on_save)
        return result

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        checkpointer: Any | None = None,
        **kwargs: Any,
    ):
        """
        Async stream with dynamic configuration support.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        # Get configuration
        configurable = (config or {}).get("configurable", {})

        supervisor_prompt = configurable.get("supervisor_prompt")
        sub_agents_config = configurable.get("sub_agents", [])
        model_name = configurable.get("model")

        collected_output = None
        # If custom sub-agents provided, create a custom graph
        if sub_agents_config:
            for i, sa in enumerate(sub_agents_config):
                logger.info(
                    "SUPERVISOR Sub-agent {i}: name={sa.get('name')}, tools={sa.get('mcp_tools', [])}"
                )

            graph = self._create_supervisor_graph(
                sub_agents_config=sub_agents_config,
                supervisor_prompt=supervisor_prompt,
                model_name=model_name,
                checkpointer=checkpointer,
            )
            async for chunk in graph.astream(input, config=config, **kwargs):
                collected_output = chunk
                yield chunk
        else:
            # Use default graph
            async for chunk in self._graph.astream(input, config=config, **kwargs):
                collected_output = chunk
                yield chunk

        # Save memories from the last output chunk
        if collected_output is not None:
            configurable = (config or {}).get("configurable", {})
            _, on_save = build_event_emitters(configurable)
            await self._save_memory_from_output(
                collected_output, original_messages, memories, user_id, config, on_save=on_save
            )

    async def astream_events(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        version: str = "v2",
        checkpointer: Any | None = None,
        **kwargs: Any,
    ):
        """
        Async stream events with dynamic configuration support.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        # Get configuration
        configurable = (config or {}).get("configurable", {})

        supervisor_prompt = configurable.get("supervisor_prompt")
        sub_agents_config = configurable.get("sub_agents", [])
        model_name = configurable.get("model")

        # If custom sub-agents provided, create a custom graph
        if sub_agents_config:
            graph = self._create_supervisor_graph(
                sub_agents_config=sub_agents_config,
                supervisor_prompt=supervisor_prompt,
                model_name=model_name,
                checkpointer=checkpointer,
            )
            async for event in graph.astream_events(
                input, config=config, version=version, **kwargs
            ):
                yield event
        else:
            async for event in self._graph.astream_events(
                input, config=config, version=version, **kwargs
            ):
                yield event

        # Save memories after streaming completes
        if configurable.get("long_term_memory", False) and user_id:
            try:
                store = self._get_langgraph_store()
                if store:
                    from core import settings as core_settings
                    from core.llm import get_model_from_config

                    model = get_model_from_config(configurable, core_settings.DEFAULT_MODEL)
                    from memory.long_term import build_event_emitters, extract_and_save_memories
                    _, on_save = build_event_emitters(configurable)
                    extract_mem = configurable.get("extract_memory", True)
                    await extract_and_save_memories(
                        store, user_id, original_messages, model, memories,
                            on_save=on_save, extract_memory=extract_mem
                    )
            except Exception as e:
                logger.warning("Failed to save memories: %s", e)


# Create singleton instance
langgraph_supervisor_agent = DynamicFlatSupervisor()
