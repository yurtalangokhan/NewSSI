"""
Configurable MCP Agent.
A simple agent that allows users to configure system prompt and select MCP tools.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from agent_composition.adapters.langchain_tool_adapter import (
    tool_bindings_to_langchain_tools,
)
from agent_composition.adapters.tools_service_gateway import ToolsServiceToolGateway
from agent_composition.domain.ports import ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agents.clarification.middleware import ask_user_alone_post_model_hook
from agents.clarification.prompt import ASK_USER_PROMPT
from agents.clarification.tool import get_clarification_tools
from agents.configurable_mcp_agent_helpers import build_compact_memory_context
from agents.connector_call_recovery import recover_connector_call
from agents.document_tools import DOCUMENT_TOOL_PROMPT, get_document_tools
from agents.knowledge import (
    KnowledgeSystemPromptBuilder,
    KnowledgeToolSelector,
    build_knowledge_binding_references,
)
from agents.lazy_agent import LazyLoadingAgent
from agents.mail_tooling import append_email_tool_policy, wrap_send_email_tool
from core import get_model, settings
from core.env import env
from core.logger import get_logger
from memory.long_term import build_event_emitters, recall_memories

logger = get_logger(__name__)

# Context variable for trusted context at invocation time (per-agent instance).
_cfg_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar(
    "_cfg_trusted_context_var", default=None
)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant.
You have access to various tools that help you accomplish tasks.
Always be helpful, accurate, and provide clear explanations."""

TOOL_USAGE_GUARDRAIL = (
    "When external lookup or computation is needed, call the appropriate tool directly. "
    "Do not say you will search or look up information without actually calling a tool first."
)

CONNECTOR_TOOL_BY_OPERATION = {
    "list_resources": "connector_list_resources",
    "read": "connector_read",
}


def _connector_tool_names(connector_bindings: list[dict[str, Any]]) -> list[str]:
    assigned_operations = {
        operation
        for binding in connector_bindings
        for operation in (binding.get("operations") or [])
    }
    return [
        tool_name
        for operation, tool_name in CONNECTOR_TOOL_BY_OPERATION.items()
        if operation in assigned_operations
    ]


def _append_connector_prompt(system_prompt: str, connector_bindings: list[dict[str, Any]]) -> str:
    if not connector_bindings:
        return system_prompt
    assignments = []
    for binding in connector_bindings:
        datasource_id = str(binding.get("datasource_id") or "").strip()
        operations = [
            operation
            for operation in (binding.get("operations") or [])
            if operation in CONNECTOR_TOOL_BY_OPERATION
        ]
        if datasource_id and operations:
            name = json.dumps(str(binding.get("name") or datasource_id), ensure_ascii=False)
            assignments.append(f"- {name} (datasource_id={datasource_id}): {', '.join(operations)}")
    if not assignments:
        return system_prompt
    guidance = (
        "Assigned connector data sources and permitted operations:\n"
        + "\n".join(assignments)
        + "\nUse connector tools only with these datasource IDs and permitted operations."
        + "\nFor questions about these sources, use connector_list_resources to discover "
        "available resources when permitted, then connector_read to retrieve actual records. "
        "Base source-data answers only on successful connector_read results. Never invent "
        "rows, role names, IDs, or claim a database was queried without a successful read. "
        "If tools are unavailable or a read fails, report the limitation instead of supplying "
        "example data. A successful resource listing is not a successful data read. "
        "Show requested lists directly in chat; create a document only when the user requests "
        "a file, using the retrieved records."
    )
    return f"{system_prompt}\n{guidance}"


def _build_default_gateway() -> ToolGateway:
    """Construct the default tools-service gateway for configured tools."""
    mcp_url = (
        getattr(settings, "TOOLS_SERVICE_URL", None)
        or getattr(settings, "MCP_SERVER_URL", None)
        or env.TOOLS_SERVICE_URL
        or env.MCP_SERVER_URL
    )
    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    return ToolsServiceToolGateway(service_url=mcp_url, internal_token=token)


class ConfigurableMCPAgent(LazyLoadingAgent):
    """
    A configurable agent with MCP tool support.

    Configuration (via agent_config):
        - system_prompt: Custom system prompt for the agent
        - mcp_tools: List of MCP tool names this agent can use

    Supports optional ToolsServiceToolGateway injection. When a gateway is
    provided, selected tools are resolved through it with TrustedContextProvider
    reading user/tenant identity from the LangGraph config at invocation time.
    """

    def __init__(self, gateway: ToolGateway | None = None) -> None:
        super().__init__()
        self._gateway = gateway or _build_default_gateway()
        self._gateway_tools: list[BaseTool] = []
        self._default_graph: CompiledStateGraph | None = None
        self._mcp_tools: dict[str, BaseTool] = {}

    @property
    def name(self) -> str:
        return "configurable-mcp-agent"

    @property
    def description(self) -> str:
        return "A configurable agent with custom system prompt and MCP tool selection"

    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return

        try:
            # Load MCP tools
            await self._load_mcp_tools()

            # Create default graph
            self._default_graph = self._create_agent_graph(
                system_prompt=DEFAULT_SYSTEM_PROMPT, mcp_tool_names=[]
            )
            self._graph = self._default_graph
            self._loaded = True

            logger.info(
                f"Configurable MCP Agent initialized with {len(self._mcp_tools)} MCP tools available"
            )

        except Exception as e:
            logger.error(f"Failed to initialize Configurable MCP Agent: {e}")
            # Create a minimal fallback graph
            self._default_graph = self._create_agent_graph(
                system_prompt=DEFAULT_SYSTEM_PROMPT, mcp_tool_names=[]
            )
            self._graph = self._default_graph
            self._loaded = True
            logger.warning("Using fallback graph without MCP tools")

    async def _load_mcp_tools(self, mcp_url: str | None = None) -> None:
        """Load tools from MCP server.

        When a ToolsServiceToolGateway is injected, tools are first resolved
        through the gateway and stored as pre-wrapped LangChain tools. The legacy
        MultiServerMCPClient path is still used to populate _mcp_tools for tools
        that need per-config wrapping (e.g. send_email).
        """
        # If a gateway is injected, use it to resolve tools first.
        if self._gateway is not None:
            try:
                await self._gateway.load()
                all_descriptors = await self._gateway.describe()
                all_keys = tuple(d.key for d in all_descriptors)
                bindings = await self._gateway.resolve(all_keys)

                def _context_provider() -> TrustedToolContext | None:
                    return _cfg_trusted_context_var.get()

                self._gateway_tools = tool_bindings_to_langchain_tools(
                    bindings, context_provider=_context_provider
                )
                logger.info(
                    "ConfigurableMCPAgent resolved %d tools via gateway",
                    len(self._gateway_tools),
                )
            except Exception as e:
                logger.warning(
                    "ConfigurableMCPAgent gateway tool resolution failed: %s. "
                    "Falling back to legacy MCP path.",
                    e,
                )
                self._gateway_tools = []

        # Always also populate _mcp_tools via legacy path for tools that need
        # per-config wrapping (e.g. send_email).

        url = mcp_url or getattr(settings, "TOOLS_SERVICE_URL", None) or settings.MCP_SERVER_URL

        candidate_urls = [url]
        parsed = urlparse(url)
        if parsed.hostname == "tools-service":
            localhost_url = parsed._replace(netloc=f"localhost:{parsed.port or 8003}").geturl()
            if localhost_url not in candidate_urls:
                candidate_urls.append(localhost_url)

        headers: dict[str, str] = {}
        internal_token = getattr(settings, "INTERNAL_SERVICE_TOKEN", None)
        if internal_token:
            headers["Authorization"] = f"Bearer {internal_token}"

        last_error: Exception | None = None
        for candidate_url in candidate_urls:
            try:
                connection: dict[str, Any] = {
                    "transport": "streamable_http",
                    "url": candidate_url,
                }
                if headers:
                    connection["headers"] = headers

                client = MultiServerMCPClient(connections={"mcp-tools": connection})

                tools = await client.get_tools()
                self._mcp_tools = {tool.name: tool for tool in tools}
                logger.info(
                    "Loaded %s MCP tools from %s: %s",
                    len(tools),
                    candidate_url,
                    list(self._mcp_tools.keys()),
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Could not load MCP tools from %s: %s", candidate_url, exc)

        if last_error is not None:
            logger.warning(f"Could not load MCP tools: {last_error}")

    async def _resolve_mcp_tool_pool(
        self, mcp_tool_names: list[str], user_id: str | None
    ) -> dict[str, BaseTool]:
        """Built-in tools + this user's connected external MCP tools (per request).

        Returns a fresh dict so per-user external tools never leak into the
        shared ``self._mcp_tools`` cache.
        """
        pool: dict[str, BaseTool] = dict(self._mcp_tools)
        if not mcp_tool_names:
            return pool
        try:
            from agents.mcp_external import load_external_mcp_tools

            external = await load_external_mcp_tools(user_id, set(mcp_tool_names))
        except Exception as exc:  # noqa: BLE001 - external servers must not break the run
            logger.warning("Could not load external MCP tools: %s", exc)
            return pool
        for name, tool in external.items():
            pool.setdefault(name, tool)
        if external:
            logger.info("Merged %s external MCP tools", len(external))
        return pool

    async def _prepare_memory_context(
        self,
        input: Any,
        config: RunnableConfig | None = None,
    ) -> tuple[Any, dict, str | None, str]:
        """Recall memories without mutating message list; return context to merge into prompt."""
        configurable = (config or {}).get("configurable", {})
        long_term_memory = configurable.get("long_term_memory", False)
        user_id = configurable.get("user_id")
        store = self._get_langgraph_store()
        memories: dict = {}

        if not long_term_memory or not store or not user_id:
            return input, memories, user_id, ""

        on_recall, _ = build_event_emitters(configurable)
        memories = await recall_memories(store, user_id, on_recall=on_recall)
        recalled_count = len(memories.get("user_facts", []))
        input = self._mark_input_with_ltm_recalled(input, recalled_count)
        memory_context = build_compact_memory_context(memories)
        return input, memories, user_id, memory_context

    def _build_compact_memory_context(self, memories: dict[str, Any]) -> str:
        """Backward-compat shim delegating to the extracted helper."""
        return build_compact_memory_context(memories)

    def _build_trusted_context(self, config: RunnableConfig | None) -> TrustedToolContext | None:
        """Build TrustedToolContext from LangGraph config for gateway tool invocation."""
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        tenant_id = configurable.get("tenant_id")
        binding_references: dict[str, str] = configurable.get("binding_references") or {}
        rag_config = configurable.get("rag_config") or {}
        binding_references = {
            **build_knowledge_binding_references(rag_config),
            **binding_references,
        }
        attachment_handles: tuple[str, ...] = tuple(
            a.get("handle") or a.get("filename") or ""
            for a in (configurable.get("mail_attachments") or [])
            if a
        )
        project_id = configurable.get("project_id")
        request_id = configurable.get("request_id")

        if not any([user_id, tenant_id, binding_references, attachment_handles, project_id]):
            return None

        from agent_composition.domain.trusted_context import build_trusted_context

        return build_trusted_context(
            user_id=user_id,
            tenant_id=tenant_id,
            binding_references=binding_references,
            attachment_handles=attachment_handles,
            project_id=project_id,
            request_id=request_id,
        )

    def _resolve_config(
        self,
        config: RunnableConfig | None,
        memory_context: str,
    ) -> tuple[dict, str, list, dict]:
        """Extract configurable dict and build the final system prompt from config + memory."""
        configurable = (config or {}).get("configurable", {})
        system_prompt = configurable.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        if memory_context:
            system_prompt = f"{system_prompt}\n{memory_context}"
        mcp_tool_names = list(configurable.get("mcp_tools") or [])
        connector_bindings = list(configurable.get("connector_bindings") or [])
        for tool_name in _connector_tool_names(connector_bindings):
            if tool_name not in mcp_tool_names:
                mcp_tool_names.append(tool_name)
        system_prompt = _append_connector_prompt(system_prompt, connector_bindings)
        mcp_tool_configs = configurable.get("mcp_tool_configs") or {}
        system_prompt = append_email_tool_policy(
            system_prompt,
            mcp_tool_names,
            mail_attachments=configurable.get("mail_attachments"),
        )
        return configurable, system_prompt, mcp_tool_names, mcp_tool_configs

    def _select_gateway_tools(self, tool_names: list[str]) -> list[BaseTool]:
        selected_names = set(tool_names)
        return [tool for tool in self._gateway_tools if tool.name in selected_names]

    def _create_agent_graph(
        self,
        system_prompt: str,
        mcp_tool_names: list[str],
        model_name: str | None = None,
        checkpointer: Any | None = None,
        extra_tools: list[BaseTool] | None = None,
        mcp_tool_configs: dict[str, Any] | None = None,
        user_id: str | None = None,
        mail_config_user_id: str | None = None,
        mail_attachments: list[dict[str, Any]] | None = None,
        mcp_tools_override: dict[str, BaseTool] | None = None,
        gateway_tools: list[BaseTool] | None = None,
    ) -> CompiledStateGraph:
        """Create an agent graph with the specified configuration.

        Args:
            system_prompt: System prompt for the agent
            mcp_tool_names: List of MCP tool names to use
            model_name: Optional model override
            checkpointer: Optional checkpointer for persistence
            extra_tools: Additional pre-resolved tools
            mcp_tool_configs: Per-tool configuration dict
            user_id: User ID for mail tool
            mail_config_user_id: Mail config user ID
            mail_attachments: Available mail attachments
            gateway_tools: Tools resolved via ToolsServiceToolGateway (prepended to agent tools)
        """
        model = get_model(model_name or settings.DEFAULT_MODEL)

        # Collect MCP tools by name from the legacy MCP cache.
        agent_tools: list[BaseTool] = []
        tool_configs = mcp_tool_configs or {}
        tool_pool = mcp_tools_override or self._mcp_tools
        for tool_name in mcp_tool_names:
            if tool_name in tool_pool:
                tool = tool_pool[tool_name]
                if tool_name == "send_email":
                    send_email_config = tool_configs.get("send_email") or {}
                    tool = wrap_send_email_tool(
                        tool,
                        mail_config_id=send_email_config.get("mail_config_id"),
                        user_id=user_id,
                        owner_user_id=mail_config_user_id,
                        mail_attachments=mail_attachments,
                    )
                agent_tools.append(tool)
            else:
                logger.warning(f"Tool '{tool_name}' not found in MCP cache")

        # Prepend gateway tools so they take precedence (same name = gateway version wins).
        if gateway_tools:
            prepared_gateway_tools = []
            for tool in gateway_tools:
                if tool.name == "send_email":
                    send_email_config = tool_configs.get("send_email") or {}
                    tool = wrap_send_email_tool(
                        tool,
                        mail_config_id=send_email_config.get("mail_config_id"),
                        user_id=user_id,
                        owner_user_id=mail_config_user_id,
                        mail_attachments=mail_attachments,
                    )
                prepared_gateway_tools.append(tool)
            gateway_names = {tool.name for tool in prepared_gateway_tools}
            agent_tools = prepared_gateway_tools + [
                tool for tool in agent_tools if tool.name not in gateway_names
            ]

        available_names = {tool.name for tool in agent_tools}
        missing_connectors = sorted(
            set(mcp_tool_names) & set(CONNECTOR_TOOL_BY_OPERATION.values()) - available_names
        )
        if missing_connectors:
            raise ValueError(
                "Assigned connector tools are unavailable: "
                + ", ".join(missing_connectors)
                + ". Check tools-service and reload the agent before querying connector data."
            )

        if agent_tools:
            system_prompt = f"{system_prompt}\n{TOOL_USAGE_GUARDRAIL}"
        elif mcp_tool_names:
            logger.warning(
                "Requested MCP tools were unavailable; continuing without tool guardrail: %s",
                mcp_tool_names,
            )

        # Append any extra tools (e.g. database_search, graph_search)
        if extra_tools:
            agent_tools.extend(extra_tools)

        document_tools = get_document_tools()
        if document_tools:
            agent_tools.extend(document_tools)
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"

        # `ask_user` needs somewhere to park the interrupt, so it only goes in
        # when this build has a checkpointer (design 5.3, E13). The guard that
        # keeps it from being called alongside other tools has no middleware
        # slot here — create_react_agent takes it as a post_model_hook, same as
        # the GraphBuilder plan-execute path.
        post_model_hook = None
        if checkpointer:
            agent_tools.extend(get_clarification_tools())
            system_prompt = f"{system_prompt}\n{ASK_USER_PROMPT}"
            post_model_hook = ask_user_alone_post_model_hook

        connector_tools = available_names & set(CONNECTOR_TOOL_BY_OPERATION.values())
        if connector_tools:
            async def connector_post_model_hook(state):
                return (
                    await ask_user_alone_post_model_hook(state)
                    or recover_connector_call(state, connector_tools)
                )

            post_model_hook = connector_post_model_hook

        agent = create_react_agent(
            model=model,
            tools=agent_tools,
            name="configurable-agent",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=checkpointer,
            post_model_hook=post_model_hook,
        )

        return agent

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        checkpointer: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Async invoke with dynamic configuration support.

        Checks for custom configuration in the config and creates
        a customized graph if needed.
        """
        await self.ensure_loaded()

        # Save original messages for memory extraction
        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        # Recall memory and merge context into system prompt (avoid extra SystemMessage).
        input, memories, user_id, memory_context = await self._prepare_memory_context(input, config)

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs = self._resolve_config(
            config,
            memory_context,
        )
        rag_config: dict = configurable.get("rag_config") or {}
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")

        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != settings.MCP_SERVER_URL:
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)

        # Resolve RAG tools and augment system prompt when rag_config is present
        rag_tool_names = KnowledgeToolSelector.select_tool_names(rag_config)
        for tool_name in rag_tool_names:
            if tool_name not in mcp_tool_names:
                mcp_tool_names.append(tool_name)
        if rag_tool_names:
            mode = KnowledgeSystemPromptBuilder.determine_mode(rag_config)
            if mode:
                system_prompt = KnowledgeSystemPromptBuilder.build_full_prompt(system_prompt, mode)

        # Resolve checkpointer: prefer explicit param, then instance-level, then graph-level
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (
                self._graph.checkpointer
                if self._graph and hasattr(self._graph, "checkpointer")
                else None
            )
        )

        # Create a custom graph whenever anything deviates from defaults
        if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
            graph = self._create_agent_graph(
                system_prompt=system_prompt,
                mcp_tool_names=mcp_tool_names,
                model_name=model_name,
                checkpointer=effective_checkpointer,
                extra_tools=None,
                mcp_tool_configs=mcp_tool_configs,
                user_id=user_id,
                mail_config_user_id=(
                    configurable.get("owner_user_id")
                    or configurable.get("mail_config_user_id")
                    or user_id
                ),
                mail_attachments=configurable.get("mail_attachments"),
                mcp_tools_override=await self._resolve_mcp_tool_pool(mcp_tool_names, user_id),
                gateway_tools=self._select_gateway_tools(mcp_tool_names),
            )

            # Set trusted context for gateway-injected tools.
            token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
            try:
                result = await graph.ainvoke(input, config=config, **kwargs)
            finally:
                _cfg_trusted_context_var.reset(token)
        else:
            # Set trusted context for gateway-injected tools even on the default graph.
            token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
            try:
                result = await self._graph.ainvoke(input, config=config, **kwargs)
            finally:
                _cfg_trusted_context_var.reset(token)

        result = self._tag_output_with_recalled_memories(result, memories)

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

        # Recall memory and merge context into system prompt (avoid extra SystemMessage).
        input, memories, user_id, memory_context = await self._prepare_memory_context(input, config)

        recall_event = self._build_memory_recall_event(memories)
        if recall_event is not None:
            yield ("custom", recall_event)

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs = self._resolve_config(
            config,
            memory_context,
        )
        rag_config: dict = configurable.get("rag_config") or {}
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")

        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != settings.MCP_SERVER_URL:
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)

        # If tools are requested but not in cache, retry loading
        if mcp_tool_names and not any(t in self._mcp_tools for t in mcp_tool_names):
            logger.warning(f"Tools {mcp_tool_names} not in cache, retrying load...")
            await self._load_mcp_tools(mcp_url)

        # Resolve RAG tools and augment system prompt when rag_config is present
        rag_tool_names = KnowledgeToolSelector.select_tool_names(rag_config)
        for tool_name in rag_tool_names:
            if tool_name not in mcp_tool_names:
                mcp_tool_names.append(tool_name)
        if rag_tool_names:
            mode = KnowledgeSystemPromptBuilder.determine_mode(rag_config)
            if mode:
                system_prompt = KnowledgeSystemPromptBuilder.build_full_prompt(system_prompt, mode)

        # Resolve checkpointer
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (
                self._graph.checkpointer
                if self._graph and hasattr(self._graph, "checkpointer")
                else None
            )
        )

        # Create a custom graph whenever anything deviates from defaults
        collected_output = None
        token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
                graph = self._create_agent_graph(
                    system_prompt=system_prompt,
                    mcp_tool_names=mcp_tool_names,
                    model_name=model_name,
                    checkpointer=effective_checkpointer,
                    extra_tools=None,
                    mcp_tool_configs=mcp_tool_configs,
                    user_id=user_id,
                    mail_config_user_id=(
                        configurable.get("owner_user_id")
                        or configurable.get("mail_config_user_id")
                        or user_id
                    ),
                    mail_attachments=configurable.get("mail_attachments"),
                    gateway_tools=self._select_gateway_tools(mcp_tool_names),
                    mcp_tools_override=await self._resolve_mcp_tool_pool(mcp_tool_names, user_id),
                )
                async for chunk in graph.astream(input, config=config, **kwargs):
                    chunk = self._tag_output_with_recalled_memories(chunk, memories)
                    collected_output = chunk
                    yield chunk
            else:
                # Use default graph
                async for chunk in self._graph.astream(input, config=config, **kwargs):
                    chunk = self._tag_output_with_recalled_memories(chunk, memories)
                    collected_output = chunk
                    yield chunk
        finally:
            _cfg_trusted_context_var.reset(token)

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

        # Recall memory and merge context into system prompt (avoid extra SystemMessage).
        input, memories, user_id, memory_context = await self._prepare_memory_context(input, config)
        recall_event = self._build_memory_recall_event(memories)

        if recall_event is not None:
            yield {"event": "custom", "data": recall_event}

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs = self._resolve_config(
            config,
            memory_context,
        )
        rag_config: dict = configurable.get("rag_config") or {}
        model_name = configurable.get("model")
        mcp_url = configurable.get("mcp_url")

        # Reload MCP tools if URL changed
        if mcp_url and mcp_url != settings.MCP_SERVER_URL:
            self._mcp_tools = {}
            await self._load_mcp_tools(mcp_url)

        # Resolve RAG tools and augment system prompt when rag_config is present
        rag_tool_names = KnowledgeToolSelector.select_tool_names(rag_config)
        for tool_name in rag_tool_names:
            if tool_name not in mcp_tool_names:
                mcp_tool_names.append(tool_name)
        if rag_tool_names:
            mode = KnowledgeSystemPromptBuilder.determine_mode(rag_config)
            if mode:
                system_prompt = KnowledgeSystemPromptBuilder.build_full_prompt(system_prompt, mode)

        # Resolve checkpointer: prefer explicit param, then instance-level, then graph-level
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (
                self._graph.checkpointer
                if self._graph and hasattr(self._graph, "checkpointer")
                else None
            )
        )

        # Create a custom graph whenever anything deviates from defaults
        token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
                graph = self._create_agent_graph(
                    system_prompt=system_prompt,
                    mcp_tool_names=mcp_tool_names,
                    model_name=model_name,
                    checkpointer=effective_checkpointer,
                    extra_tools=None,
                    mcp_tool_configs=mcp_tool_configs,
                    user_id=user_id,
                    mail_config_user_id=(
                        configurable.get("owner_user_id")
                        or configurable.get("mail_config_user_id")
                        or user_id
                    ),
                    mail_attachments=configurable.get("mail_attachments"),
                    gateway_tools=self._select_gateway_tools(mcp_tool_names),
                    mcp_tools_override=await self._resolve_mcp_tool_pool(mcp_tool_names, user_id),
                )
                async for event in graph.astream_events(
                    input, config=config, version=version, **kwargs
                ):
                    yield event
            else:
                # Use default graph
                async for event in self._graph.astream_events(
                    input, config=config, version=version, **kwargs
                ):
                    yield event
        finally:
            _cfg_trusted_context_var.reset(token)

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
                logger.warning(
                    f"[ConfigurableMCPAgent] Memory save after stream_events failed: {e}"
                )


# Create the agent instance
configurable_mcp_agent = ConfigurableMCPAgent()
