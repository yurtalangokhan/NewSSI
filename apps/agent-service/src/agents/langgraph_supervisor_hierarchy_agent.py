"""
Dynamic Pipeline Supervisor Agent.
Creates a sequential pipeline of stages where each stage's output feeds into the next.
Supports dynamic stage configuration with MCP tools per stage.
"""

from __future__ import annotations

import hashlib
import json as json_module
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel
from langgraph_supervisor import create_supervisor

from agent_composition.adapters.langchain_tool_adapter import (
    tool_bindings_to_langchain_tools,
)
from agent_composition.domain.ports import ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agents.lazy_agent import LazyLoadingAgent
from core import get_model, settings
from core.env import env
from core.logger import get_logger
from memory.long_term import build_event_emitters

logger = get_logger(__name__)

# Context variable for trusted context at invocation time.
_pipe_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar(
    "_pipe_trusted_context_var", default=None
)

# Default stage prompts for common use cases
DEFAULT_STAGE_PROMPTS = {
    "enricher": "You are a project enricher. Analyze the input and expand it with more details, requirements, and specifications.",
    "implementer": "You are a code implementer. Take the enriched project specification and create the actual implementation using the available tools.",
    "documenter": "You are a technical writer. Create comprehensive documentation for the implementation including README, API docs, and usage examples.",
    "deployer": "You are a deployment specialist. Prepare and deploy the project using git and other deployment tools.",
}

# Default pipeline configuration
DEFAULT_PIPELINE_STAGES = [
    {"name": "enricher", "system_prompt": DEFAULT_STAGE_PROMPTS["enricher"], "mcp_tools": []}
]


class DynamicPipelineSupervisor(LazyLoadingAgent):
    """
    A dynamic pipeline supervisor that executes stages sequentially.

    Configuration (via agent_config):
        - pipeline_stages: List of stage configurations
            - name: Stage name (used as node identifier)
            - system_prompt: System prompt for this stage's agent
            - mcp_tools: List of MCP tool names to enable for this stage
        - retry_count: Number of retries on stage failure (default: 2)
        - on_error: Error handling strategy ('abort' or 'skip', default: 'abort')

    Supports optional ToolsServiceToolGateway injection for trusted-context tool path.
    """

    def __init__(self, gateway: ToolGateway | None = None) -> None:
        super().__init__()
        self._gateway = gateway
        self._gateway_tools_map: dict[str, Any] = {}  # name -> BaseTool
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_tools: dict[str, Any] = {}
        self._mcp_cleanup = None
        self._graph_cache: dict[str, CompiledStateGraph | Pregel] = {}

    @property
    def name(self) -> str:
        return "langgraph-supervisor-hierarchy-agent"

    @property
    def description(self) -> str:
        return "A dynamic pipeline supervisor that executes stages sequentially with MCP tools"

    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return

        try:
            # Try to load MCP tools
            await self._load_mcp_tools()

            # Create default graph with a single stage
            self._default_graph = self._create_pipeline_graph(DEFAULT_PIPELINE_STAGES)
            self._graph = self._default_graph
            self._loaded = True

            logger.info(
                "Dynamic Pipeline Supervisor initialized with %s MCP tools available",
                len(self._mcp_tools),
            )

        except Exception as e:
            logger.error("Failed to initialize Dynamic Pipeline Supervisor: %s", e)
            # Create a minimal fallback graph
            self._default_graph = self._create_fallback_graph()
            self._graph = self._default_graph
            self._loaded = True
            logger.warning("Using fallback graph without MCP tools")

    def _build_trusted_context(self, config: RunnableConfig | None) -> TrustedToolContext | None:
        """Build TrustedToolContext from LangGraph config for gateway tool invocation."""
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        tenant_id = configurable.get("tenant_id")
        binding_references: dict = configurable.get("binding_references") or {}
        project_id = configurable.get("project_id")
        request_id = configurable.get("request_id")

        if not any([user_id, tenant_id, binding_references, project_id]):
            return None

        from agent_composition.domain.trusted_context import build_trusted_context

        return build_trusted_context(
            user_id=user_id,
            tenant_id=tenant_id,
            binding_references=binding_references,
            project_id=project_id,
            request_id=request_id,
        )

    async def _load_mcp_tools(self) -> None:
        """Load tools from MCP server.

        When a ToolsServiceToolGateway is injected, tools are resolved through
        the gateway and stored as a name->tool map in _gateway_tools_map.
        """
        # If a gateway is injected, resolve tools through it.
        if self._gateway is not None:
            try:
                await self._gateway.load()
                all_descriptors = await self._gateway.describe()
                all_keys = tuple(d.key for d in all_descriptors)
                bindings = await self._gateway.resolve(all_keys)

                def _context_provider() -> TrustedToolContext | None:
                    return _pipe_trusted_context_var.get()

                gateway_tools = tool_bindings_to_langchain_tools(
                    bindings, context_provider=_context_provider
                )
                self._gateway_tools_map = {t.name: t for t in gateway_tools}
                logger.info(
                    "DynamicPipelineSupervisor resolved %d tools via gateway",
                    len(self._gateway_tools_map),
                )
            except Exception as e:
                logger.warning(
                    "DynamicPipelineSupervisor gateway tool resolution failed: %s. "
                    "Falling back to legacy MCP path.",
                    e,
                )
                self._gateway_tools_map = {}

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            mcp_url = env.MCP_SERVER_URL
            token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
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

            logger.info("Loaded %s MCP tools for pipeline", len(self._mcp_tools))

        except Exception as e:
            logger.warning("Failed to load MCP tools: %s", e)
            self._mcp_tools = {}

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
            prompt="You are a supervisor. Currently no pipeline stages are configured.",
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    def _pipeline_cache_key(
        self,
        stages: list[dict[str, Any]],
        model_name: str | None = None,
        checkpointer: Any | None = None,
    ) -> str:
        """Generate a stable cache key from pipeline configuration.

        The key is derived from stage names, system prompts, MCP tool
        lists, the model name, and the checkpointer type so that graphs
        compiled with different configurations are kept separate while
        identical configurations reuse the same compiled graph (and
        therefore the same sub-graph node UUIDs).
        """
        key_data = {
            "stages": [
                {
                    "name": s.get("name", ""),
                    "system_prompt": s.get("system_prompt", ""),
                    "mcp_tools": sorted(s.get("mcp_tools", [])),
                    "model": s.get("model", ""),
                }
                for s in stages
            ],
            "model": model_name or settings.DEFAULT_MODEL,
            "checkpointer": type(checkpointer).__name__ if checkpointer else "none",
        }
        raw = json_module.dumps(key_data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _create_pipeline_graph(
        self,
        stages: list[dict[str, Any]],
        model_name: str | None = None,
        retry_count: int = 2,
        on_error: str = "abort",
        checkpointer: Any | None = None,
    ) -> CompiledStateGraph | Pregel:
        """
        Create a pipeline graph with the specified stages.

        Compiled graphs are cached by configuration so that repeated
        calls with the same stages / model / checkpointer reuse the
        same graph instance.  This is critical for LangGraph's
        checkpoint system because each compilation assigns new UUIDs to
        sub-graph nodes; reusing the graph keeps the namespace UUIDs
        stable and allows message history to accumulate correctly.

        Args:
            stages: List of stage configurations, each with:
                - name: Stage identifier
                - system_prompt: Prompt for this stage
                - mcp_tools: List of MCP tool names
                - model: (Optional) Model override for this specific stage.
                         If omitted or empty, the supervisor's model (model_name)
                         is used as fallback.
            model_name: Model for the supervisor itself (and default for stages)
            retry_count: Number of retries per stage
            on_error: Error handling ('abort' or 'skip')
            checkpointer: Optional checkpointer for persistence

        Returns:
            Compiled pipeline graph
        """
        if not stages:
            return self._default_graph or self._create_fallback_graph()

        # ── Cache lookup ──────────────────────────────────────────────
        cache_key = self._pipeline_cache_key(stages, model_name, checkpointer)
        if cache_key in self._graph_cache:
            logger.info("PIPELINE Reusing cached graph (key=%s)", cache_key[:12])
            return self._graph_cache[cache_key]

        supervisor_model_name = model_name or settings.DEFAULT_MODEL
        supervisor_model = get_model(supervisor_model_name)

        # Create agents for each stage
        stage_agents = []

        for stage_config in stages:
            stage_name = stage_config.get("name", f"stage_{len(stage_agents)}")
            system_prompt = stage_config.get("system_prompt", f"You are the {stage_name} agent.")
            mcp_tool_names = stage_config.get("mcp_tools", [])

            # Per-stage model: use stage-specific model if provided, otherwise fall back to supervisor model
            stage_model_name = stage_config.get("model") or supervisor_model_name
            stage_model = get_model(stage_model_name)

            if stage_config.get("model"):
                logger.info(
                    "[PIPELINE] Stage '%s': using custom model '%s' (overrides supervisor model '%s')",
                    stage_name,
                    stage_model_name,
                    supervisor_model_name,
                )
            else:
                logger.info(
                    "[PIPELINE] Stage '%s': using supervisor model '%s' (no override)",
                    stage_name,
                    supervisor_model_name,
                )

            # Get requested MCP tools (gateway tools take precedence over legacy MCP tools).
            stage_tools = []
            for tool_name in mcp_tool_names:
                if tool_name in self._gateway_tools_map:
                    stage_tools.append(self._gateway_tools_map[tool_name])
                elif tool_name in self._mcp_tools:
                    stage_tools.append(self._mcp_tools[tool_name])
                else:
                    logger.warning("MCP tool '%s' not found for stage '%s'", tool_name, stage_name)

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

            # Create the stage agent with its own model
            agent = create_react_agent(
                model=stage_model,
                tools=stage_tools,
                name=f"stage-{stage_name}",
                prompt=SystemMessage(content=enhanced_system_prompt),
            )

            # Wrap with stage identification (no skip_stream for visibility)
            wrapped_agent = agent.with_config(run_name=f"sub-agent-{stage_name}", tags=[])

            stage_agents.append((stage_name, wrapped_agent))

        # Use provided checkpointer or create a MemorySaver fallback
        if checkpointer is None:
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()
        else:
            logger.info(
                f"[PIPELINE] Compiling graph with provided checkpointer: {type(checkpointer).__name__}"
            )
            logger.info(
                "PIPELINE Compiling graph with provided checkpointer: {type(checkpointer).__name__}"
            )

        # Extract just the agents from the tuples (drop the wrapped_agent, use original)
        agents_only = [agent for (stage_name, agent) in stage_agents]

        # Build agent descriptions for supervisor prompt
        agent_descriptions = []
        for stage_config in stages:
            stage_name = stage_config.get("name", "stage")
            mcp_tool_names = stage_config.get("mcp_tools", [])
            tool_list = ", ".join(mcp_tool_names) if mcp_tool_names else "no tools"
            agent_descriptions.append(f"- stage-{stage_name}: (tools: {tool_list})")

        # Build stage list for the prompt
        stage_list = "\n".join(
            [f"{i + 1}. stage-{name}" for i, (name, _) in enumerate(stage_agents)]
        )

        # Create a single flat supervisor that manages all stage agents
        # This is similar to how langgraph_supervisor_agent works
        main_prompt = f"""You are a pipeline supervisor coordinating a sequential workflow of specialized agents.

Available agents and their tools:
{chr(10).join(agent_descriptions)}

Pipeline execution order:
{stage_list}

INSTRUCTIONS:
1. Start by delegating the user's request to stage-{stage_agents[0][0]} (first stage)
2. After each stage completes, pass its results to the next stage agent
3. Continue through all stages in order
4. After the final stage completes, provide a comprehensive summary

IMPORTANT:
- Always delegate to the appropriate stage agent - do NOT answer directly
- Each agent MUST use their tools to complete tasks
- Wait for each stage to complete before moving to the next"""

        workflow = create_supervisor(
            agents_only,
            model=supervisor_model,
            prompt=main_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        compiled = workflow.compile(checkpointer=checkpointer)
        self._graph_cache[cache_key] = compiled

        # Log model summary for all stages
        model_summary = []
        for stage_config in stages:
            sname = stage_config.get("name", "?")
            smodel = stage_config.get("model") or supervisor_model_name
            model_summary.append(f"{sname}={smodel}")
        logger.info(
            "[PIPELINE] Graph created (key=%s). Supervisor=%s, Stages: %s",
            cache_key[:12],
            supervisor_model_name,
            ", ".join(model_summary),
        )
        return compiled

    def get_graph(self) -> CompiledStateGraph | Pregel:
        """Return the default graph."""
        if not self._loaded:
            raise RuntimeError("Agent not loaded. Call load() first.")
        return self._graph

    def create_configured_graph(
        self,
        pipeline_stages: list[dict[str, Any]],
        model_name: str | None = None,
        retry_count: int = 2,
        on_error: str = "abort",
    ) -> CompiledStateGraph | Pregel:
        """
        Create a pipeline graph with the specified configuration.

        Args:
            pipeline_stages: List of stage configs, each with:
                - name: Stage identifier
                - system_prompt: Prompt for this stage
                - mcp_tools: List of MCP tool names
            model_name: Optional model override
            retry_count: Retries per stage (default: 2)
            on_error: Error strategy ('abort' or 'skip')

        Returns:
            Compiled pipeline graph
        """
        return self._create_pipeline_graph(
            pipeline_stages, model_name=model_name, retry_count=retry_count, on_error=on_error
        )

    def get_available_mcp_tools(self) -> list[str]:
        """Get list of available MCP tool names."""
        return list(self._mcp_tools.keys())

    async def ensure_loaded(self) -> None:
        """Ensure the agent is loaded."""
        if not self._loaded:
            await self.load()

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        checkpointer: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Async invoke with dynamic configuration support.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Inject memory context
        input, memories, user_id = await self._inject_memory_into_input(input, config)

        configurable = (config or {}).get("configurable", {})
        pipeline_stages = configurable.get("pipeline_stages", [])
        model_name = configurable.get("model")

        token = _pipe_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if pipeline_stages:
                graph = self._create_pipeline_graph(
                    stages=pipeline_stages,
                    model_name=model_name,
                    checkpointer=checkpointer,
                )
                result = await graph.ainvoke(input, config=config, **kwargs)
            else:
                result = await self._graph.ainvoke(input, config=config, **kwargs)
        finally:
            _pipe_trusted_context_var.reset(token)

        # Save memories from output
        configurable = (config or {}).get("configurable", {})
        _, on_save = build_event_emitters(configurable)
        await self._save_memory_from_output(
            result, original_messages, memories, user_id, config, on_save=on_save
        )
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

        configurable = (config or {}).get("configurable", {})

        logger.info(
            f"[PIPELINE] astream called with configurable keys: {list(configurable.keys())}"
        )
        pipeline_stages = configurable.get("pipeline_stages", [])
        model_name = configurable.get("model")

        collected_output = None
        token = _pipe_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if pipeline_stages:
                for i, stage in enumerate(pipeline_stages):
                    logger.info(
                        "[PIPELINE] Stage %s: name=%s, tools=%s",
                        i,
                        stage.get("name"),
                        stage.get("mcp_tools", []),
                    )

                graph = self._create_pipeline_graph(
                    stages=pipeline_stages,
                    model_name=model_name,
                    checkpointer=checkpointer,
                )
                async for chunk in graph.astream(input, config=config, **kwargs):
                    collected_output = chunk
                    yield chunk
            else:
                async for chunk in self._graph.astream(input, config=config, **kwargs):
                    collected_output = chunk
                    yield chunk
        finally:
            _pipe_trusted_context_var.reset(token)

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
        checkpointer: Any | None = None,
        version: str = "v2",
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

        configurable = (config or {}).get("configurable", {})

        logger.info(
            f"[PIPELINE] astream_events called with configurable keys: {list(configurable.keys())}"
        )
        logger.info(
            "PIPELINE astream_events called with configurable keys: {list(configurable.keys())}"
        )

        pipeline_stages = configurable.get("pipeline_stages", [])
        model_name = configurable.get("model")

        token = _pipe_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if pipeline_stages:
                graph = self._create_pipeline_graph(
                    stages=pipeline_stages,
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
        finally:
            _pipe_trusted_context_var.reset(token)

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
                        store,
                        user_id,
                        original_messages,
                        model,
                        memories,
                        on_save=on_save,
                        extract_memory=extract_mem,
                    )
            except Exception as e:
                logger.warning("Failed to save memories: %s", e)

    async def cleanup(self) -> None:
        """Cleanup MCP connections."""
        if self._mcp_cleanup:
            try:
                await self._mcp_cleanup()
            except Exception:
                logger.error("error")


# Create singleton instance
langgraph_supervisor_hierarchy_agent = DynamicPipelineSupervisor()
