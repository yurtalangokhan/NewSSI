"""DynamicAgent - runtime-configurable LangGraph agent backed by AgentDefinition."""

from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar
import hashlib
import json
from typing import Any

from config_manager import env
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agent_composition.adapters.langchain_tool_adapter import (
    tool_bindings_to_langchain_tools,
)
from agent_composition.adapters.tools_service_gateway import ToolsServiceToolGateway
from agent_composition.application.compose_agent import AgentComposer, register_agent_class
from agent_composition.domain.definitions import RuntimePolicyConfig
from agent_composition.domain.ports import ToolArtifactPolicy, ToolGateway
from agent_composition.domain.trusted_context import TrustedToolContext
from agent_composition.runtime import ComposedAgent
from agents.graphs.builder import GraphBuilder
from agents.knowledge.tool_selector import build_knowledge_binding_references
from agents.primitives.base import LazyLoadingAgent
from core.observability.logger import get_logger
from core.security.mcp.mcp_url_policy import default_mcp_url
from infrastructure.llm.llm import get_model_from_config
from schemas.agent_graphs import GraphSchemaType, get_schema
from service.knowledge_evidence.factory import build_knowledge_evidence_artifact_policy

logger = get_logger(__name__)

#: How many distinct runtime graphs one agent keeps compiled. A single
#: conversation reuses one entry; the rest of the window covers a user
#: switching model or an agent serving a handful of concurrent callers.
RUNTIME_GRAPH_CACHE_SIZE = 8

#: The configurable keys _prepare_graph_build actually reads. Anything else
#: in `configurable` (thread_id, trace ids, the caller's token) does not
#: change the compiled graph and must not split the cache.
_GRAPH_INPUT_KEYS = frozenset(
    {
        "graph_schema",
        "system_prompt",
        "model",
        "model_version",
        "model_provider",
        "temperature",
        "llm_instance",
        "memory_type",
        "mcp_tools",
        "mcp_tool_configs",
        "mail_attachments",
        "rag_config",
        "user_id",
        "owner_user_id",
        "supervisor_prompt",
        "sub_agents",
        "sub_agent_ids",
        "pipeline_prompt",
        "stages",
        "reflection_prompt",
        "max_iterations",
    }
)


# Per-definition-ID cache so we don't reload MCP tools on every request.
# Key = definition_id (str UUID), Value = loaded DynamicAgent instance.
_agent_cache: dict[str, DynamicAgent] = {}

# Context variable for trusted context at invocation time.
# Set by DynamicAgent before calling graph.ainvoke; read by
# LangChainToolAdapter context providers inside tool nodes.
_trusted_context_var: ContextVar[TrustedToolContext | None] = ContextVar("_trusted_context_var", default=None)


def get_cached_agent(definition_id: str) -> DynamicAgent | None:
    """Return a previously loaded DynamicAgent if present in cache."""
    return _agent_cache.get(definition_id)


async def cache_agent(definition_id: str, agent: DynamicAgent) -> None:
    """Store a loaded DynamicAgent in cache, releasing the one it replaces.

    Overwriting the entry used to drop the previous agent without closing it,
    so the MCP connections and gateway clients its composed runtime owned were
    leaked on every definition update.
    """
    previous = _agent_cache.get(definition_id)
    _agent_cache[definition_id] = agent
    if previous is not None and previous is not agent:
        close = getattr(previous, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                logger.warning("Failed to close the replaced agent for %s", definition_id, exc_info=True)


def invalidate_agent_cache(definition_id: str) -> None:
    """Remove agent from cache (call after definition update/delete)."""
    _agent_cache.pop(definition_id, None)


class _Unset:
    """Marker: no gateway injected and none built yet (see ``_gateway``)."""


_UNSET = _Unset()


def _build_default_gateway() -> ToolGateway:
    """Construct the default ``ToolsServiceToolGateway`` for tool resolution.

    Used when a ``DynamicAgent`` is created without an explicit gateway. The
    gateway is the canonical, trusted-context-aware tool loader (wired in
    ASC-2D); the legacy ``MultiServerMCPClient`` path was removed in ASC-5.
    """
    mcp_url = default_mcp_url()
    token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
    return ToolsServiceToolGateway(service_url=mcp_url, internal_token=token)


def _knowledge_tool_names(rag_config: dict[str, Any]) -> list[str]:
    if not rag_config:
        return []
    from agents.knowledge.tool_selector import KnowledgeToolSelector

    return KnowledgeToolSelector.select_tool_names(rag_config)


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
        definition_repository: Any | None = None,
        artifact_policy: ToolArtifactPolicy | None = None,
    ):
        super().__init__()
        self._config = agent_config or {}
        # The gateway is the canonical tool loader; build a default one when the
        # caller does not inject a specific gateway (ASC-5 cutover).
        self._gateway_instance: ToolGateway | _Unset | None = gateway if gateway is not None else _UNSET
        # Knowledge tools return evidence as structured content; this policy
        # persists it and references it from the ToolMessage artifact.
        self._artifact_policy = artifact_policy or build_knowledge_evidence_artifact_policy()
        self._gateway_tools: list[Any] = []  # Pre-resolved LangChain tools from gateway
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_tools_map: dict[str, Any] = {}
        self._definition_repository = definition_repository
        # Composed runtime (ASC-4) that owns the lifecycle/resources behind the
        # existing resolution and cache contracts.
        self._composed: ComposedAgent | None = None

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
            logger.info(
                "DynamicAgent '%s' loaded with schema: %s",
                self.name,
                self._config.get("graph_schema", "zero_shot"),
            )
        except Exception:
            # Do not cache a placeholder: a transient load failure (MCP
            # server briefly unreachable, bad definition) used to become a
            # permanently degraded "helpful assistant" that answered every
            # future turn as if nothing were wrong. Reset so the next
            # ensure_loaded() call retries instead of reusing a half state,
            # and let the caller see the real error.
            self._default_graph = None
            self._graph = None
            self._composed = None
            self._loaded = False
            logger.exception("DynamicAgent '%s' load failed", self.name)
            raise

    def _build_trusted_context(self, config: RunnableConfig | None) -> TrustedToolContext | None:
        """Build TrustedToolContext from LangGraph config for gateway tool invocation."""
        configurable = (config or {}).get("configurable", {})
        user_id = configurable.get("user_id")
        tenant_id = configurable.get("tenant_id")
        binding_references: dict[str, str] = configurable.get("binding_references") or {}
        rag_config = configurable.get("rag_config") or self._config.get("rag_config") or {}
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
                    bindings,
                    context_provider=_context_provider,
                    artifact_policy=self._artifact_policy,
                )
                logger.info(
                    "DynamicAgent '%s' resolved %d tools via gateway",
                    self.name,
                    len(self._gateway_tools),
                )
            except Exception as e:
                logger.warning(
                    "DynamicAgent '%s' gateway tool resolution failed: %s. Falling back to no tools.",
                    self.name,
                    e,
                )
                self._gateway_tools = []

        # Built-in tool loading is performed exclusively through the injected
        # ToolsServiceToolGateway (wired in ASC-2D); the legacy
        # MultiServerMCPClient path was removed in ASC-5. ``_mcp_tools_map``
        # therefore only carries tools from *connected external* MCP servers,
        # which the gateway does not know about, so GraphBuilder still sees
        # them without shadowing any gateway-resolved built-in.
        self._mcp_tools_map = {}
        # Only the servers this agent's own tool selection names. Without
        # wanted_names the loader opened a session against every CONNECTED
        # external provider in the table and waited on each of them, so one
        # agent's load fanned out across servers it never uses.
        wanted = {str(n) for n in (self._config.get("mcp_tools") or []) if n}
        if not wanted:
            return
        try:
            from agents.tooling.mcp_external import load_external_mcp_tools

            external = await load_external_mcp_tools(None, wanted_names=wanted)
            if external:
                self._mcp_tools_map.update(external)
                logger.info(
                    "DynamicAgent '%s' loaded %d external MCP tools",
                    self.name,
                    len(external),
                )
        except Exception as e:
            logger.warning("DynamicAgent '%s' could not load external MCP tools: %s", self.name, e)

    def _create_graph_from_config(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> CompiledStateGraph | Pregel:
        builder, schema_type, build_config = self._prepare_graph_build(runtime_config=runtime_config)
        return builder.build(schema_type, build_config)

    async def _create_graph_from_config_async(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> CompiledStateGraph | Pregel:
        builder, schema_type, build_config = self._prepare_graph_build(runtime_config=runtime_config)
        builder.repository = self._definition_repository
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
            model=get_model_from_config(effective_config, env.DEFAULT_MODEL),
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
        rag_tool_names = _knowledge_tool_names(rag_config)

        configured_mcp_tools = list(effective_config.get("mcp_tools", []))
        for tool_name in rag_tool_names:
            if tool_name not in configured_mcp_tools:
                configured_mcp_tools.append(tool_name)
        if schema_type == GraphSchemaType.ZERO_SHOT and configured_mcp_tools:
            logger.info(
                "Upgrading DynamicAgent '%s' from zero_shot to react because tools or RAG are configured",
                self.name,
            )
            schema_type = GraphSchemaType.REACT

        if schema_type == GraphSchemaType.REACT:
            build_config["mcp_tools"] = configured_mcp_tools
            build_config["system_prompt"] = system_prompt
        elif schema_type == GraphSchemaType.SUPERVISOR:
            build_config["name"] = self.name
            build_config["supervisor_prompt"] = self._config.get("supervisor_prompt", "You are a team supervisor.")
            build_config["sub_agents"] = effective_config.get("sub_agents", [])
            build_config["sub_agent_ids"] = effective_config.get("sub_agent_ids", [])
            build_config["model"] = effective_config.get("model")
        elif schema_type == GraphSchemaType.PIPELINE:
            build_config["name"] = self.name
            build_config["pipeline_prompt"] = effective_config.get("pipeline_prompt", "Process through all stages.")
            build_config["stages"] = effective_config.get("stages", [])
            build_config["sub_agent_ids"] = effective_config.get("sub_agent_ids", [])
            build_config["model"] = effective_config.get("model")
        elif schema_type == GraphSchemaType.PLAN_EXECUTE:
            build_config["system_prompt"] = system_prompt
            build_config["mcp_tools"] = configured_mcp_tools
        elif schema_type == GraphSchemaType.SELF_REFLECT:
            build_config["system_prompt"] = system_prompt
            build_config["reflection_prompt"] = effective_config.get(
                "reflection_prompt", "Review and improve this response."
            )
            build_config["max_iterations"] = effective_config.get("max_iterations", 3)
        else:
            build_config["system_prompt"] = system_prompt

        return builder, schema_type, build_config

    def _runtime_graph_cache_key(self, configurable: dict[str, Any]) -> str | None:
        """A stable key for a runtime graph, or None when it must not be cached.

        Only the fields _prepare_graph_build actually reads take part, so an
        unrelated per-request value (thread_id, a trace id) does not split the
        cache. Identity is part of the key: a graph built with one user's mail
        tooling must never be handed to another.
        """
        relevant = {key: value for key, value in configurable.items() if key in _GRAPH_INPUT_KEYS}
        # A per-turn payload of file bytes: it would never produce a hit, and
        # caching it would pin those bytes for the life of the entry.
        if relevant.get("mail_attachments"):
            return None
        try:
            # No `default=`: a value that will not serialise (a live model
            # instance, say) is one this cache cannot reason about, so the
            # build is simply not cached rather than keyed on its repr.
            canonical = json.dumps(relevant, sort_keys=True)
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _cached_runtime_graph(self, configurable: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build the override graph for this turn, reusing an identical one.

        Compiling walks the schema, resolves and binds the tool list and
        constructs the model. None of that changes between two turns of the
        same conversation, but a chat turn always carries `model`, so this
        ran on every single turn.
        """
        cache = getattr(self, "_runtime_graphs", None)
        if cache is None:
            cache = OrderedDict()
            self._runtime_graphs = cache

        key = self._runtime_graph_cache_key(configurable)
        if key is None:
            return self._create_graph_from_config(runtime_config=configurable)

        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached

        graph = self._create_graph_from_config(runtime_config=configurable)
        cache[key] = graph
        while len(cache) > RUNTIME_GRAPH_CACHE_SIZE:
            cache.popitem(last=False)
        return graph

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
        if any(k in configurable for k in runtime_keys) or (has_configured_mail_tool and configurable.get("user_id")):
            return self._cached_runtime_graph(configurable)

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
            await self._save_memory_from_output(result, original_messages, memories, user_id, config)

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
                await self._save_memory_from_output(None, original_messages, memories, user_id, config)
            except Exception as e:
                logger.warning("Memory save after stream failed: %s", e)


# Register DynamicAgent with agent_composition facade to invert dependency
register_agent_class(DynamicAgent)
