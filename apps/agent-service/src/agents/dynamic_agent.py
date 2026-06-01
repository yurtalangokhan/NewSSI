"""DynamicAgent - runtime-configurable LangGraph agent backed by AgentDefinition."""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agents.lazy_agent import LazyLoadingAgent
from agents.graphs.builder import GraphBuilder
from agents.graphs.schemas import GraphSchemaType, get_schema
from core import settings
from core.llm import get_model, get_model_from_config
from core.logger import get_logger
from memory.long_term import build_event_emitters

logger = get_logger(__name__)

# Per-definition-ID cache so we don't reload MCP tools on every request.
# Key = definition_id (str UUID), Value = loaded DynamicAgent instance.
_agent_cache: dict[str, "DynamicAgent"] = {}


def get_cached_agent(definition_id: str) -> "DynamicAgent | None":
    """Return a previously loaded DynamicAgent if present in cache."""
    return _agent_cache.get(definition_id)


def cache_agent(definition_id: str, agent: "DynamicAgent") -> None:
    """Store a loaded DynamicAgent in cache."""
    _agent_cache[definition_id] = agent


def invalidate_agent_cache(definition_id: str) -> None:
    """Remove agent from cache (call after definition update/delete)."""
    _agent_cache.pop(definition_id, None)


class DynamicAgent(LazyLoadingAgent):
    """
    A dynamic agent whose graph schema, tools, and prompts are driven by an
    AgentDefinition stored in the database.

    The DynamicAgent wraps LazyLoadingAgent and delegates graph construction to
    GraphBuilder.  The resulting compiled graph is cached in the instance after
    the first `load()` call, so repeated requests share the same graph.
    """

    def __init__(self, agent_config: dict[str, Any] | None = None):
        super().__init__()
        self._config = agent_config or {}
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_tools_map: dict[str, Any] = {}
        self._load_failed = False

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

    async def load(self) -> None:
        if self._loaded:
            return

        try:
            await self._load_mcp_tools()
            self._default_graph = self._create_graph_from_config()
            self._graph = self._default_graph
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

    async def _load_mcp_tools(self) -> None:
        """Load all available MCP tools into the internal map."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            mcp_url = (
                getattr(settings, "TOOLS_SERVICE_URL", None)
                or getattr(settings, "MCP_SERVER_URL", None)
                or os.environ.get("TOOLS_SERVICE_URL")
                or os.environ.get("MCP_SERVER_URL")
                or "http://localhost:8002/mcp"
            )

            client = MultiServerMCPClient(
                connections={
                    "mcp-tools": {
                        "transport": "streamable_http",
                        "url": mcp_url,
                    }
                }
            )

            tools = await client.get_tools()
            for tool in tools:
                self._mcp_tools_map[tool.name] = tool

            logger.info(
                "Loaded %d MCP tools for DynamicAgent '%s' from %s",
                len(tools),
                self.name,
                mcp_url,
            )
        except Exception as e:
            logger.warning("Could not load MCP tools for DynamicAgent '%s': %s", self.name, e)

    def _create_graph_from_config(
        self,
        *,
        runtime_config: dict[str, Any] | None = None,
    ) -> CompiledStateGraph | Pregel:
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
        )

        build_config: dict[str, Any] = {}
        rag_config = effective_config.get("rag_config") or {}
        rag_tools = []
        if rag_config:
            try:
                from agents.knowledge.tool_selector import KnowledgeToolSelector

                rag_tools = KnowledgeToolSelector.select_tools(rag_config)
            except Exception as e:
                logger.warning("Failed to resolve knowledge tools for DynamicAgent '%s': %s", self.name, e)

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
            build_config["supervisor_prompt"] = self._config.get(
                "supervisor_prompt", "You are a team supervisor."
            )
            build_config["sub_agents"] = effective_config.get("sub_agents", [])
            build_config["model"] = effective_config.get("model")
        elif schema_type == GraphSchemaType.PIPELINE:
            build_config["pipeline_prompt"] = effective_config.get(
                "pipeline_prompt", "Process through all stages."
            )
            build_config["stages"] = effective_config.get("stages", [])
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

        return builder.build(schema_type, build_config)

    def _create_fallback_graph(self) -> CompiledStateGraph:
        """Minimal fallback graph when load fails."""
        return GraphBuilder(
            model=get_model(settings.DEFAULT_MODEL),
            system_prompt="You are a helpful assistant.",
            mcp_tools_map={},
            checkpointer=self._checkpointer if hasattr(self, "_checkpointer") else None,
        ).build("zero_shot")

    def _get_runtime_graph(self, config: RunnableConfig | None) -> CompiledStateGraph | Pregel:
        configurable = (config or {}).get("configurable", {})
        if not configurable:
            return self._graph

        # Only build an override graph if runtime model routing fields are present.
        if any(k in configurable for k in ("model", "llm_instance", "system_prompt", "mcp_tools")):
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

        graph = self._get_runtime_graph(config)
        result = await graph.ainvoke(input, config=config, **kwargs)

        if memories is not None and user_id:
            configurable = (config or {}).get("configurable", {})
            _, on_save = build_event_emitters(configurable)
            await self._save_memory_from_output(result, original_messages, memories, user_id, config, on_save=on_save)

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

        graph = self._get_runtime_graph(config)
        async for event in graph.astream(input, config=config, **kwargs):
            yield event

        if memories is not None and user_id:
            # Best-effort memory save; we don't have final output here but
            # LazyLoadingAgent._save_memory_from_output handles None gracefully.
            try:
                configurable = (config or {}).get("configurable", {})
                _, on_save = build_event_emitters(configurable)
                await self._save_memory_from_output(None, original_messages, memories, user_id, config, on_save=on_save)
            except Exception as e:
                logger.warning("Memory save after stream failed: %s", e)
