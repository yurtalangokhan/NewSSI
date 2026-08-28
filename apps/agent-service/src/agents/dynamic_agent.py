"""DynamicAgent - runtime-configurable LangGraph agent backed by AgentDefinition."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agent_composition.adapters.langchain_tool_adapter import (
    tool_bindings_to_langchain_tools,
)
from agent_composition.adapters.tools_service_gateway import ToolsServiceToolGateway
from agent_composition.application.compose_agent import AgentComposer
from agent_composition.domain.definitions import RuntimePolicyConfig
from agent_composition.domain.ports import ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agent_composition.runtime import ComposedAgent
from agents.graphs.builder import GraphBuilder
from agents.graphs.schemas import GraphSchemaType, get_schema
from agents.lazy_agent import LazyLoadingAgent
from core import settings
from core.env import env
from core.llm import get_model, get_model_from_config
from core.logger import get_logger
from memory.long_term import build_event_emitters

logger = get_logger(__name__)

# Per-definition-ID cache so we don't reload MCP tools on every request.
# Key = definition_id (str UUID), Value = loaded DynamicAgent instance.
_agent_cache: dict[str, DynamicAgent] = {}

# Context variable for trusted context at invocation time.
# Set by DynamicAgent before calling graph.ainvoke; read by
# LangChainToolAdapter context providers inside tool nodes.
_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar(
    "_trusted_context_var", default=None
)


def get_cached_agent(definition_id: str) -> DynamicAgent | None:
    """Return a previously loaded DynamicAgent if present in cache."""
    return _agent_cache.get(definition_id)


def cache_agent(definition_id: str, agent: DynamicAgent) -> None:
    """Store a loaded DynamicAgent in cache."""
    _agent_cache[definition_id] = agent


def invalidate_agent_cache(definition_id: str) -> None:
    """Remove agent from cache (call after definition update/delete)."""
    _agent_cache.pop(definition_id, None)


def _build_default_gateway() -> ToolGateway:
    """Construct the default ``ToolsServiceToolGateway`` for tool resolution.

    Used when a ``DynamicAgent`` is created without an explicit gateway. The
    gateway is the canonical, trusted-context-aware tool loader (wired in
    ASC-2D); the legacy ``MultiServerMCPClient`` path was removed in ASC-5.
    """
    mcp_url = (
        getattr(settings, "TOOLS_SERVICE_URL", None)
        or getattr(settings, "MCP_SERVER_URL", None)
        or env.TOOLS_SERVICE_URL
        or env.MCP_SERVER_URL
        or "http://localhost:8003/mcp"
    )
    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    return ToolsServiceToolGateway(service_url=mcp_url, internal_token=token)


class DynamicAgent(LazyLoadingAgent):
    """
    A dynamic agent whose graph schema, tools, and prompts are driven by an
    AgentDefinition stored in the database.

    The DynamicAgent wraps LazyLoadingAgent and delegates graph construction to
    GraphBuilder.  The resulting compiled graph is cached in the instance after
    the first `load()` call, so repeated requests share the same graph.

    Supports optional `ToolsServiceToolGateway` injection for the trusted-context
    tool path. When a gateway is provided, selected tools are resolved through it
    and wrapped as LangChain tools using TrustedContextProvider (which reads
    user/tenant identity from the LangGraph config at invocation time).
    """

    def __init__(
        self,
        agent_config: dict[str, Any] | None = None,
        gateway: ToolGateway | None = None,
    ):
        super().__init__()
        self._config = agent_config or {}
        # The gateway is the canonical tool loader; build a default one when the
        # caller does not inject a specific gateway (ASC-5 cutover).
        self._gateway = gateway or _build_default_gateway()
        self._gateway_tools: list[Any] = []  # Pre-resolved LangChain tools from gateway
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_tools_map: dict[str, Any] = {}
        self._load_failed = False
        # Composed runtime (ASC-4) that owns the lifecycle/resources behind the
        # existing resolution and cache contracts.
        self._composed: ComposedAgent | None = None

    @property
    def name(self) -> str:
        return self._config.get("name", "dynamic-agent")

    @property
    def description(self) -> str:
        schema_type = self._config.get("graph_schema", "zero_shot")
        schema = get_schema(schema_type)
        return schema.description if schema else "Dynamic agent"

    @property
    def agent_type(self) -> str:
        return "dynamic"

    @property
    def graph_schema(self) -> str:
        return self._config.get("graph_schema", "zero_shot")

    @property
    def load_failed(self) -> bool:
        """Whether the last ``load()`` fell back to a minimal graph."""
        return self._load_failed

    @property
    def has_checkpointer(self) -> bool:
        """Whether a checkpointer is attached to this agent."""
        return getattr(self, "_checkpointer", None) is not None

    @property
    def composed_agent(self) -> ComposedAgent | None:
        """The composed runtime (ASC-4) that owns this agent's resources."""
        return self._composed

    async def close(self) -> None:
        """Release runtime resources owned by the composed agent."""
        if self._composed is not None:
            await self._composed.close()
        self._loaded = False

    async def load(self) -> None:
        if self._loaded:
            return

        try:
            await self._load_mcp_tools()
            self._default_graph = await self._create_graph_from_config_async()
            self._graph = self._default_graph
            # Assemble the composed runtime (ASC-4) around the built graph so the
            # ComposedAgent owns the lifecycle/resources behind the existing
            # resolution and cache contracts. The legacy (input, config) execution
            # interface is preserved via ``self._graph``.
            self._composed = AgentComposer.assemble(
                graph=self._default_graph,
                runtime_policy_config=RuntimePolicyConfig(),
                checkpointer=self._checkpointer if hasattr(self, "_checkpointer") else None,
            )
            await self._composed.load()
            self._loaded = True
            self._load_failed = False
            logger.info(
                "DynamicAgent '%s' loaded with schema: %s",
                self.name,
                self._config.get("graph_schema", "zero_shot"),
            )
        except Exception as e:
            logger.error("DynamicAgent load failed: %s", e)
            self._default_graph = self._create_fallback_graph()
            self._graph = self._default_graph
            self._loaded = True
            self._load_failed = True

    def _build_trusted_context(self, config: RunnableConfig | None) -> TrustedToolContext | None:
        """Build TrustedToolContext from LangGraph config for gateway tool invocation."""
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        tenant_id = configurable.get("tenant_id")
        binding_references: dict[str, str] = configurable.get("binding_references") or {}
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

    async def _load_mcp_tools(self) -> None:
        """Load all available MCP tools into the internal map.

        Tools are resolved exclusively through the injected
        ToolsServiceToolGateway (wired in ASC-2D) and stored as pre-wrapped
        LangChain tools in ``_gateway_tools``. The legacy ``MultiServerMCPClient``
        path was removed in ASC-5; the gateway is the canonical, trusted-context
        aware tool loader.
        """
        # If a gateway is injected, use it to resolve tools.
        if self._gateway is not None:
            try:
                await self._gateway.load()
                all_descriptors = await self._gateway.describe()
                all_keys = tuple(d.key for d in all_descriptors)
                bindings = await self._gateway.resolve(all_keys)

                def _context_provider() -> TrustedToolContext | None:
                    return _trusted_context_var.get()

                self._gateway_tools = tool_bindings_to_langchain_tools(
                    bindings, context_provider=_context_provider
                )
                logger.info(
                    "DynamicAgent '%s' resolved %d tools via gateway",
                    self.name,
                    len(self._gateway_tools),
                )
            except Exception as e:
                logger.warning(
                    "DynamicAgent '%s' gateway tool resolution failed: %s. "
                    "Falling back to no tools.",
                    self.name,
                    e,
                )
                self._gateway_tools = []

        # Tool loading is performed exclusively through the injected
        # ToolsServiceToolGateway (wired in ASC-2D). The legacy
        # MultiServerMCPClient path was removed in ASC-5; the gateway is the
        # canonical, trusted-context-aware tool loader. ``_mcp_tools_map`` is
        # kept empty so GraphBuilder only consults the gateway-resolved tools.
        self._mcp_tools_map = {}

    def _create_graph_from_config(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> CompiledStateGraph | Pregel:
        builder, schema_type, build_config = self._prepare_graph_build(
            runtime_config=runtime_config
        )
        return builder.build(schema_type, build_config)

    async def _create_graph_from_config_async(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> CompiledStateGraph | Pregel:
        builder, schema_type, build_config = self._prepare_graph_build(
            runtime_config=runtime_config
        )
        from agents.storage.repository import AgentDefinitionRepository

        builder.repository = AgentDefinitionRepository()
        return await builder.build_async(schema_type, build_config)

    def _prepare_graph_build(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> tuple[GraphBuilder, GraphSchemaType, dict[str, Any]]:
        effective_config = {**self._config, **(runtime_config or {})}
        schema_type_str = effective_config.get("graph_schema", "zero_shot")

        try:
            schema_type = GraphSchemaType(schema_type_str)
        except ValueError:
            logger.warning("Unknown schema type '%s', falling back to zero_shot", schema_type_str)
            schema_type = GraphSchemaType.ZERO_SHOT

        schema = get_schema(schema_type)
        default_system_prompt = (
            schema.default_system_prompt
            if schema and getattr(schema, "default_system_prompt", None)
            else "You are a helpful AI assistant."
        )
        system_prompt = effective_config.get("system_prompt") or default_system_prompt

        builder = GraphBuilder(
            model=get_model_from_config(effective_config, settings.DEFAULT_MODEL),
            system_prompt=system_prompt,
            mcp_tools_map=self._mcp_tools_map,
            memory_enabled=effective_config.get("memory_type") == "long_term",
            checkpointer=self._checkpointer if hasattr(self, "_checkpointer") else None,
            gateway_tools=self._gateway_tools,
        )

        build_config: dict[str, Any] = {
            "mcp_tool_configs": effective_config.get("mcp_tool_configs") or {},
            "user_id": effective_config.get("owner_user_id") or effective_config.get("user_id"),
            "mail_attachments": effective_config.get("mail_attachments") or [],
        }
        rag_config = effective_config.get("rag_config") or {}
        rag_tools = []
        if rag_config:
            try:
                from agents.knowledge.tool_selector import KnowledgeToolSelector

                rag_tools = KnowledgeToolSelector.select_tools(rag_config)
            except Exception as e:
                logger.warning(
                    "Failed to resolve knowledge tools for DynamicAgent '%s': %s", self.name, e
                )

        configured_mcp_tools = effective_config.get("mcp_tools", [])
        if schema_type == GraphSchemaType.ZERO_SHOT and (configured_mcp_tools or rag_tools):
            logger.info(
                "Upgrading DynamicAgent '%s' from zero_shot to react because tools or RAG are configured",
                self.name,
            )
            schema_type = GraphSchemaType.REACT

        if schema_type == GraphSchemaType.REACT:
            build_config["mcp_tools"] = configured_mcp_tools
            build_config["system_prompt"] = system_prompt
            build_config["extra_tools"] = rag_tools
        elif schema_type == GraphSchemaType.SUPERVISOR:
            build_config["name"] = self.name
            build_config["supervisor_prompt"] = self._config.get(
                "supervisor_prompt", "You are a team supervisor."
            )
            build_config["sub_agents"] = effective_config.get("sub_agents", [])
            build_config["sub_agent_ids"] = effective_config.get("sub_agent_ids", [])
            build_config["model"] = effective_config.get("model")
        elif schema_type == GraphSchemaType.PIPELINE:
            build_config["name"] = self.name
            build_config["pipeline_prompt"] = effective_config.get(
                "pipeline_prompt", "Process through all stages."
            )
            build_config["stages"] = effective_config.get("stages", [])
            build_config["sub_agent_ids"] = effective_config.get("sub_agent_ids", [])
            build_config["model"] = effective_config.get("model")
            build_config["extra_tools"] = rag_tools
        elif schema_type == GraphSchemaType.PLAN_EXECUTE:
            build_config["system_prompt"] = system_prompt
            build_config["mcp_tools"] = effective_config.get("mcp_tools", [])
            build_config["extra_tools"] = rag_tools
        elif schema_type == GraphSchemaType.SELF_REFLECT:
            build_config["system_prompt"] = system_prompt
            build_config["reflection_prompt"] = effective_config.get(
                "reflection_prompt", "Review and improve this response."
            )
            build_config["max_iterations"] = effective_config.get("max_iterations", 3)
        else:
            build_config["system_prompt"] = system_prompt

        return builder, schema_type, build_config

    def _create_fallback_graph(self) -> CompiledStateGraph:
        """Minimal fallback graph when load fails."""
        return GraphBuilder(
            model=get_model(settings.DEFAULT_MODEL),
            system_prompt="You are a helpful assistant.",
            mcp_tools_map={},
            checkpointer=self._checkpointer if hasattr(self, "_checkpointer") else None,
            gateway_tools=self._gateway_tools,
        ).build("zero_shot")

    def _get_runtime_graph(self, config: RunnableConfig | None) -> CompiledStateGraph | Pregel:
        configurable = (config or {}).get("configurable", {})
        if not configurable:
            return self._graph

        # Only build an override graph if runtime model routing fields are present.
        has_configured_mail_tool = "send_email" in (self._config.get("mcp_tools") or []) and bool(
            (self._config.get("mcp_tool_configs") or {}).get("send_email")
        )
        runtime_keys = {
            "model",
            "llm_instance",
            "system_prompt",
            "mcp_tools",
            "mcp_tool_configs",
            "mail_attachments",
        }
        if any(k in configurable for k in runtime_keys) or (
            has_configured_mail_tool and configurable.get("user_id")
        ):
            return self._create_graph_from_config(runtime_config=configurable)

        return self._graph

    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        await self.ensure_loaded()

        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        input, memories, user_id = await self._inject_memory_into_input(input, config)

        # Build trusted context from config for gateway-injected tools.
        token = _trusted_context_var.set(self._build_trusted_context(config))

        try:
            graph = self._get_runtime_graph(config)
            result = await graph.ainvoke(input, config=config, **kwargs)
        finally:
            _trusted_context_var.reset(token)

        if memories is not None and user_id:
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
        **kwargs: Any,
    ):
        """Delegate streaming to the underlying compiled graph."""
        await self.ensure_loaded()

        original_messages = []
        if isinstance(input, dict) and "messages" in input:
            original_messages = list(input["messages"])

        input, memories, user_id = await self._inject_memory_into_input(input, config)

        # Build trusted context from config for gateway-injected tools.
        token = _trusted_context_var.set(self._build_trusted_context(config))

        try:
            graph = self._get_runtime_graph(config)
            async for event in graph.astream(input, config=config, **kwargs):
                yield event
        finally:
            _trusted_context_var.reset(token)

        if memories is not None and user_id:
            # Best-effort memory save; we don't have final output here but
            # LazyLoadingAgent._save_memory_from_output handles None gracefully.
            try:
                configurable = (config or {}).get("configurable", {})
                _, on_save = build_event_emitters(configurable)
                await self._save_memory_from_output(
                    None, original_messages, memories, user_id, config, on_save=on_save
                )
            except Exception as e:
                logger.warning("Memory save after stream failed: %s", e)
