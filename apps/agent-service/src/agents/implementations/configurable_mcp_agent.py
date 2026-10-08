"""
Configurable MCP Agent.
A simple agent that allows users to configure system prompt and select MCP tools.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextvars import ContextVar
import hashlib
import json
import time
from typing import Any, NamedTuple
from urllib.parse import urlparse

from config_manager import env
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
from agent_composition.domain.ports import ToolArtifactPolicy, ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agents.clarification.middleware import ask_user_alone_post_model_hook
from agents.clarification.prompt import ASK_USER_PROMPT
from agents.clarification.tool import get_clarification_tools
from agents.knowledge import (
    KnowledgeSystemPromptBuilder,
    KnowledgeToolSelector,
    build_knowledge_binding_references,
)
from agents.primitives.base import LazyLoadingAgent
from agents.tooling.attachment_manifest import attachment_aware_prompt, has_attachment_tool
from agents.tooling.connector_call_recovery import recover_connector_call
from agents.tooling.document_tools import DOCUMENT_TOOL_PROMPT, get_document_tools
from agents.tooling.mail_tooling import append_email_tool_policy, wrap_send_email_tool
from core.observability.logger import get_logger
from core.security.mcp.mcp_url_policy import default_mcp_url, resolve_allowed_mcp_url
from infrastructure.llm import get_model
from memory.long_term import (
    build_event_emitters,
    extract_memories_for_turn,
    latest_human_message_text,
    recall_memories,
    render_memory_context,
)
from service.knowledge_evidence.factory import build_knowledge_evidence_artifact_policy

#: MCP agents parse tool-call-like tags out of their context, so recalled
#: facts get every angle bracket neutralized (not just the XML delimiter the
#: default renderer strips) and a tighter, count-based cap instead of the
#: XML style's plain character budget.
_MCP_MEMORY_MAX_FACTS = 8
logger = get_logger(__name__)

# How long a single MCP tool listing may take before the run gives up.
MCP_TOOL_FETCH_TIMEOUT_SECONDS = 20.0

#: Minimum gap between reloads triggered by the same still-missing tool name.
TOOL_RELOAD_COOLDOWN_SECONDS = 60.0


class _RunConfig(NamedTuple):
    configurable: dict[str, Any]
    system_prompt: str
    mcp_tool_names: list[str]
    mcp_tool_configs: dict[str, Any]
    model_name: str | None


# Context variable for trusted context at invocation time (per-agent instance).
_cfg_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar("_cfg_trusted_context_var", default=None)

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
        operation for binding in connector_bindings for operation in (binding.get("operations") or [])
    }
    return [
        tool_name for operation, tool_name in CONNECTOR_TOOL_BY_OPERATION.items() if operation in assigned_operations
    ]


def _append_connector_prompt(system_prompt: str, connector_bindings: list[dict[str, Any]]) -> str:
    if not connector_bindings:
        return system_prompt
    assignments = []
    for binding in connector_bindings:
        datasource_id = str(binding.get("datasource_id") or "").strip()
        operations = [
            operation for operation in (binding.get("operations") or []) if operation in CONNECTOR_TOOL_BY_OPERATION
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


class _Unset:
    """Marker: no gateway injected and none built yet (see ``_gateway``)."""


_UNSET = _Unset()


def _build_default_gateway() -> ToolGateway:
    """Construct the default tools-service gateway for configured tools."""
    mcp_url = default_mcp_url()
    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    return ToolsServiceToolGateway(service_url=mcp_url, internal_token=token)


#: How many distinct override-graph configurations one agent instance keeps
#: compiled at once. Mirrors DynamicAgent.RUNTIME_GRAPH_CACHE_SIZE.
OVERRIDE_GRAPH_CACHE_SIZE = 8


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

    def __init__(
        self,
        gateway: ToolGateway | None = None,
        artifact_policy: ToolArtifactPolicy | None = None,
    ) -> None:
        super().__init__()
        self._gateway_instance: ToolGateway | _Unset | None = gateway if gateway is not None else _UNSET
        # Knowledge tools return evidence as structured content; this policy
        # persists it and references it from the ToolMessage artifact.
        self._artifact_policy = artifact_policy or build_knowledge_evidence_artifact_policy()
        self._gateway_tools: list[BaseTool] = []
        self._default_graph: CompiledStateGraph | None = None
        self._mcp_tools: dict[str, BaseTool] = {}
        self._reload_attempted_at: dict[str, float] = {}

    @property
    def _gateway(self) -> ToolGateway | None:
        """The tools-service gateway, built on first use.

        Building it resolves ``INTERNAL_TOOLS_SERVICE_URL``, which an image started without
        configuration (the Makefile smoke's ``import app``) does not have, and this module
        creates an agent at import time -- so construction must not need it. An explicit
        ``None`` (a test opting out of the gateway) is kept as is.
        """
        gateway = getattr(self, "_gateway_instance", _UNSET)
        if isinstance(gateway, _Unset):
            gateway = _build_default_gateway()
            self._gateway_instance = gateway
        return gateway

    @_gateway.setter
    def _gateway(self, gateway: ToolGateway | None) -> None:
        self._gateway_instance = gateway

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
            self._default_graph = self._create_agent_graph(system_prompt=DEFAULT_SYSTEM_PROMPT, mcp_tool_names=[])
            self._graph = self._default_graph
            self._loaded = True

            logger.info(f"Configurable MCP Agent initialized with {len(self._mcp_tools)} MCP tools available")

        except Exception as e:
            logger.error(f"Failed to initialize Configurable MCP Agent: {e}")
            # Create a minimal fallback graph
            self._default_graph = self._create_agent_graph(system_prompt=DEFAULT_SYSTEM_PROMPT, mcp_tool_names=[])
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
                    bindings,
                    context_provider=_context_provider,
                    artifact_policy=self._artifact_policy,
                )
                logger.info(
                    "ConfigurableMCPAgent resolved %d tools via gateway",
                    len(self._gateway_tools),
                )
            except Exception as e:
                logger.warning(
                    "ConfigurableMCPAgent gateway tool resolution failed: %s. Falling back to legacy MCP path.",
                    e,
                )
                self._gateway_tools = []

        # Always also populate _mcp_tools via legacy path for tools that need
        # per-config wrapping (e.g. send_email).

        url = mcp_url or default_mcp_url()

        candidate_urls = [url]
        parsed = urlparse(url)
        if parsed.hostname == "tools-service":
            localhost_url = parsed._replace(netloc=f"localhost:{parsed.port or 8003}").geturl()
            if localhost_url not in candidate_urls:
                candidate_urls.append(localhost_url)

        headers: dict[str, str] = {}
        internal_token = getattr(env, "INTERNAL_SERVICE_TOKEN", None)
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

                # Bounded: an unreachable or slow MCP server used to hold
                # this await open for as long as the transport allowed, and
                # this runs on the request path.
                tools = await asyncio.wait_for(client.get_tools(), timeout=MCP_TOOL_FETCH_TIMEOUT_SECONDS)
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

    async def _resolve_mcp_tool_pool(self, mcp_tool_names: list[str], user_id: str | None) -> dict[str, BaseTool]:
        """Built-in tools + this user's connected external MCP tools (per request).

        Returns a fresh dict so per-user external tools never leak into the
        shared ``self._mcp_tools`` cache.
        """
        pool: dict[str, BaseTool] = dict(self._mcp_tools)
        if not mcp_tool_names:
            return pool
        try:
            from agents.tooling.mcp_external import load_external_mcp_tools

            external = await load_external_mcp_tools(user_id, set(mcp_tool_names))
        except Exception as exc:
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

        query = latest_human_message_text(input.get("messages", []) if isinstance(input, dict) else [])
        on_recall, _ = build_event_emitters(configurable)
        memories = await recall_memories(user_id, query, on_recall=on_recall)
        recalled_count = len(memories.get("user_facts", []))
        input = self._mark_input_with_ltm_recalled(input, recalled_count)
        memory_context = self._build_compact_memory_context(memories)
        return input, memories, user_id, memory_context

    def _build_compact_memory_context(self, memories: dict[str, Any]) -> str:
        """Tool-call-safe rendering: every angle bracket is neutralized (not
        just the XML delimiter the default renderer strips) since this
        agent parses tool-call-like tags out of its context."""
        return render_memory_context(
            memories.get("user_facts", []),
            style="plain",
            strip_angle_brackets=True,
            max_facts=_MCP_MEMORY_MAX_FACTS,
        )

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
            a.get("handle") or a.get("filename") or "" for a in (configurable.get("mail_attachments") or []) if a
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

    async def _ensure_tools_available(self, tool_names: list[str], mcp_url: str) -> None:
        """Retry tool resolution when a requested name is missing.

        ``self._gateway_tools``/``self._mcp_tools`` are populated once by
        ``_load_mcp_tools`` (at ``load()`` time, or here). A tools-service
        that was unreachable or mid-reload at that moment otherwise leaves
        every gateway-hosted tool (database_search, graph_search, connector
        tools, ...) missing for the life of this process, since nothing else
        ever calls ``_load_mcp_tools`` again.

        Each missing name triggers at most one reload per
        ``TOOL_RELOAD_COOLDOWN_SECONDS``, so a tool tools-service genuinely
        lacks does not cost a tools/list round trip on every turn.
        """
        known = {tool.name for tool in self._gateway_tools} | set(self._mcp_tools)
        missing = set(tool_names) - known
        now = time.monotonic()
        # Entries expire by age, not by whether the current call still misses
        # them: this agent is shared across personas, so one turn's missing
        # set says nothing about another's.
        self._reload_attempted_at = {
            name: attempted
            for name, attempted in self._reload_attempted_at.items()
            if now - attempted < TOOL_RELOAD_COOLDOWN_SECONDS
        }
        retryable = missing - self._reload_attempted_at.keys()
        if not retryable:
            return
        await self._load_mcp_tools(mcp_url)
        self._reload_attempted_at.update(dict.fromkeys(retryable, now))

    async def _resolve_run_config(self, config: RunnableConfig | None, memory_context: str) -> _RunConfig:
        """Everything one invocation needs: prompt, tools and model, with tools loaded."""
        configurable, system_prompt, mcp_tool_names, mcp_tool_configs = self._resolve_config(
            config,
            memory_context,
        )
        rag_config: dict = configurable.get("rag_config") or {}
        # Allow-listed only: a disallowed value (e.g. an attacker-supplied
        # host) resolves back to the same default URL that is already
        # cached below, so it can never trigger INTERNAL_SERVICE_TOKEN
        # being sent elsewhere, nor a reload of the shared self._mcp_tools
        # cache on account of a value nobody legitimately configured. See
        # core/mcp_url_policy.py for what this does and does not cover.
        mcp_url = resolve_allowed_mcp_url(configurable.get("mcp_url"))

        # Reload MCP tools if URL changed
        if mcp_url != default_mcp_url():
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

        await self._ensure_tools_available(mcp_tool_names, mcp_url)

        return _RunConfig(
            configurable=configurable,
            system_prompt=system_prompt,
            mcp_tool_names=mcp_tool_names,
            mcp_tool_configs=mcp_tool_configs,
            model_name=configurable.get("model"),
        )

    @staticmethod
    def _override_graph_cache_key(
        *,
        system_prompt: str,
        mcp_tool_names: list[str],
        model_name: str | None,
        mcp_tool_configs: dict[str, Any] | None,
        user_id: str | None,
        mail_config_user_id: str | None,
        mail_attachments: list[dict[str, Any]] | None,
    ) -> str | None:
        """A stable key for an override graph, or None when it must not be cached.

        Identity is part of the key: a graph built with one user's mail
        tooling (mail_config_user_id) or resolved external tools (user_id)
        must never be handed to another. mail_attachments is a per-turn
        payload of file bytes -- it would never produce a hit, and caching it
        would pin those bytes in the entry for as long as it lives.
        """
        if mail_attachments:
            return None
        relevant = {
            "system_prompt": system_prompt,
            "mcp_tool_names": sorted(mcp_tool_names),
            "model_name": model_name,
            "mcp_tool_configs": mcp_tool_configs or {},
            "user_id": user_id,
            "mail_config_user_id": mail_config_user_id,
        }
        try:
            canonical = json.dumps(relevant, sort_keys=True)
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _cached_override_graph(
        self,
        *,
        system_prompt: str,
        mcp_tool_names: list[str],
        model_name: str | None,
        checkpointer: Any | None,
        mcp_tool_configs: dict[str, Any] | None,
        user_id: str | None,
        mail_config_user_id: str | None,
        mail_attachments: list[dict[str, Any]] | None,
    ) -> CompiledStateGraph:
        """Build this turn's override graph, reusing an identical one.

        Building resolves every named external MCP tool through a fresh
        session (_resolve_mcp_tool_pool -> load_external_mcp_tools, one
        network round trip per tool) and constructs a new react agent.
        None of that changes between two turns carrying the same
        configuration, but any turn that selects a tool or a non-default
        prompt takes this path, which in practice is every turn once a
        persona has any tools configured at all.
        """
        cache: OrderedDict[str, CompiledStateGraph] | None = getattr(self, "_override_graphs", None)
        if cache is None:
            cache = OrderedDict()
            self._override_graphs = cache

        key = self._override_graph_cache_key(
            system_prompt=system_prompt,
            mcp_tool_names=mcp_tool_names,
            model_name=model_name,
            mcp_tool_configs=mcp_tool_configs,
            user_id=user_id,
            mail_config_user_id=mail_config_user_id,
            mail_attachments=mail_attachments,
        )
        if key is not None:
            cached = cache.get(key)
            if cached is not None:
                cache.move_to_end(key)
                return cached

        graph = self._create_agent_graph(
            system_prompt=system_prompt,
            mcp_tool_names=mcp_tool_names,
            model_name=model_name,
            checkpointer=checkpointer,
            extra_tools=None,
            mcp_tool_configs=mcp_tool_configs,
            user_id=user_id,
            mail_config_user_id=mail_config_user_id,
            mail_attachments=mail_attachments,
            mcp_tools_override=await self._resolve_mcp_tool_pool(mcp_tool_names, user_id),
            gateway_tools=self._select_gateway_tools(mcp_tool_names),
        )
        if key is not None:
            cache[key] = graph
            while len(cache) > OVERRIDE_GRAPH_CACHE_SIZE:
                cache.popitem(last=False)
        return graph

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
        model = get_model(model_name or env.DEFAULT_MODEL)

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
            agent_tools = prepared_gateway_tools + [tool for tool in agent_tools if tool.name not in gateway_names]

        available_names = {tool.name for tool in agent_tools}
        missing_connectors = sorted(set(mcp_tool_names) & set(CONNECTOR_TOOL_BY_OPERATION.values()) - available_names)
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
                return await ask_user_alone_post_model_hook(state) or recover_connector_call(state, connector_tools)

            post_model_hook = connector_post_model_hook

        agent = create_react_agent(
            model=model,
            tools=agent_tools,
            name="configurable-agent",
            prompt=(
                attachment_aware_prompt(system_prompt)
                if has_attachment_tool(agent_tools)
                else SystemMessage(content=system_prompt)
            ),
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

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs, model_name = await self._resolve_run_config(
            config, memory_context
        )

        # Resolve checkpointer: prefer explicit param, then instance-level, then graph-level
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (self._graph.checkpointer if self._graph and hasattr(self._graph, "checkpointer") else None)
        )

        # Create a custom graph whenever anything deviates from defaults
        if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
            graph = await self._cached_override_graph(
                system_prompt=system_prompt,
                mcp_tool_names=mcp_tool_names,
                model_name=model_name,
                checkpointer=effective_checkpointer,
                mcp_tool_configs=mcp_tool_configs,
                user_id=user_id,
                mail_config_user_id=(
                    configurable.get("owner_user_id") or configurable.get("mail_config_user_id") or user_id
                ),
                mail_attachments=configurable.get("mail_attachments"),
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
        await self._save_memory_from_output(result, original_messages, memories, user_id, config)
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

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs, model_name = await self._resolve_run_config(
            config, memory_context
        )

        # Resolve checkpointer
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (self._graph.checkpointer if self._graph and hasattr(self._graph, "checkpointer") else None)
        )

        # Create a custom graph whenever anything deviates from defaults
        collected_output = None
        token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
                graph = await self._cached_override_graph(
                    system_prompt=system_prompt,
                    mcp_tool_names=mcp_tool_names,
                    model_name=model_name,
                    checkpointer=effective_checkpointer,
                    mcp_tool_configs=mcp_tool_configs,
                    user_id=user_id,
                    mail_config_user_id=(
                        configurable.get("owner_user_id") or configurable.get("mail_config_user_id") or user_id
                    ),
                    mail_attachments=configurable.get("mail_attachments"),
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
            await self._save_memory_from_output(collected_output, original_messages, memories, user_id, config)

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

        configurable, system_prompt, mcp_tool_names, mcp_tool_configs, model_name = await self._resolve_run_config(
            config, memory_context
        )

        # Resolve checkpointer: prefer explicit param, then instance-level, then graph-level
        effective_checkpointer = (
            checkpointer
            or getattr(self, "_checkpointer", None)
            or (self._graph.checkpointer if self._graph and hasattr(self._graph, "checkpointer") else None)
        )

        # Create a custom graph whenever anything deviates from defaults
        token = _cfg_trusted_context_var.set(self._build_trusted_context(config))
        try:
            if system_prompt != DEFAULT_SYSTEM_PROMPT or mcp_tool_names:
                graph = await self._cached_override_graph(
                    system_prompt=system_prompt,
                    mcp_tool_names=mcp_tool_names,
                    model_name=model_name,
                    checkpointer=effective_checkpointer,
                    mcp_tool_configs=mcp_tool_configs,
                    user_id=user_id,
                    mail_config_user_id=(
                        configurable.get("owner_user_id") or configurable.get("mail_config_user_id") or user_id
                    ),
                    mail_attachments=configurable.get("mail_attachments"),
                )
                async for event in graph.astream_events(input, config=config, version=version, **kwargs):
                    yield event
            else:
                # Use default graph
                async for event in self._graph.astream_events(input, config=config, version=version, **kwargs):
                    yield event
        finally:
            _cfg_trusted_context_var.reset(token)

        # Save memories after streaming completes
        if configurable.get("long_term_memory", False) and user_id:
            try:
                store = self._get_langgraph_store()
                if store:
                    from config_manager import env

                    from infrastructure.llm.llm import get_model_from_config

                    model = get_model_from_config(configurable, env.DEFAULT_MODEL)
                    await extract_memories_for_turn(user_id, configurable, original_messages, model, memories)
            except Exception as e:
                logger.warning(f"[ConfigurableMCPAgent] Memory save after stream_events failed: {e}")


# Create the agent instance
configurable_mcp_agent = ConfigurableMCPAgent()
