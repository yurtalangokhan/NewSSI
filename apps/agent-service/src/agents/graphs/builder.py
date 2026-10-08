"""Graph builder factory - builds LangGraph graphs from schema definitions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from error_contract.agent import GraphBuilderError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agents.graphs.builder_helpers import (
    MAX_NESTED_SUB_AGENT_DEPTH,
    agent_def_to_config,
)
from agents.graphs.strategies.registry import get_strategy
from agents.tooling.mail_tooling import maybe_wrap_mcp_tool
from core.observability.logger import get_logger
from schemas.agent_graphs import (
    GraphSchemaType,
    get_schema,
)

logger = get_logger(__name__)

# A supervisor/pipeline sub-agent chain that loops back on itself (directly
# or indirectly) used to recurse with no bound at all in both the DB-loading
# step below and the nested-strategy-construction step in
# strategies/supervisor.py and strategies/pipeline.py.


class GraphBuilder:
    """
    Builds LangGraph graphs from configuration.

    Takes a graph schema type and configuration, returns a compiled graph.
    """

    def __init__(
        self,
        model: BaseChatModel | None = None,
        system_prompt: str = "You are a helpful AI assistant.",
        tools: list[Any] | None = None,
        mcp_tools_map: dict[str, Any] | None = None,
        memory_enabled: bool = False,
        checkpointer: Any | None = None,
        repository: Any | None = None,
        gateway_tools: list[Any] | None = None,
        owner_ids: list[str] | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.mcp_tools_map = mcp_tools_map or {}
        self.memory_enabled = memory_enabled
        self.checkpointer = checkpointer
        self.repository = repository  # NEW: For loading sub-agents from DB
        # Which identities may run the definitions this graph pulls from the
        # database. ``None`` means the caller already authorised the whole
        # graph (e.g. a persona whose execution was checked upstream); a list
        # scopes every lookup, which is what a client-supplied flow spec needs.
        self.owner_ids = owner_ids
        # Gateway-injected tools (from ToolsServiceToolGateway, pre-resolved as BaseTool).
        # These are prepended to the tools list so they take precedence over
        # mcp_tools_map lookups for the same tool name.
        self.gateway_tools = gateway_tools or []

    def _get_tools_for_names(
        self,
        tool_names: list[str],
        *,
        tool_configs: dict[str, Any] | None = None,
        user_id: str | None = None,
        mail_attachments: list[dict[str, Any]] | None = None,
    ) -> list[Any]:
        """Get tool instances from names using the tools map."""
        tools = []
        for name in tool_names:
            if name in self.mcp_tools_map:
                tools.append(
                    maybe_wrap_mcp_tool(
                        tool_name=name,
                        tool=self.mcp_tools_map[name],
                        tool_configs=tool_configs,
                        user_id=user_id,
                        mail_attachments=mail_attachments,
                    )
                )
            else:
                logger.warning(f"Tool '{name}' not found in tools map")
        return tools

    def _get_model(self, model_name: str | None = None) -> BaseChatModel:
        """Get model instance, using override or default."""
        if model_name:
            from infrastructure.llm import get_model

            return get_model(model_name)
        if self.model:
            return self.model
        from config_manager import env

        from infrastructure.llm import get_model

        return get_model(env.DEFAULT_MODEL)

    def build(
        self, schema_type: str | GraphSchemaType, config: dict[str, Any] | None = None
    ) -> CompiledStateGraph | Pregel:
        """
        Build a graph from schema type and config.

        Args:
            schema_type: Type of graph schema to build
            config: Configuration for the graph

        Returns:
            Compiled graph
        """
        config = config or {}

        if isinstance(schema_type, str):
            try:
                schema_type = GraphSchemaType(schema_type)
            except ValueError:
                raise GraphBuilderError(f"Unknown schema type: {schema_type}") from None

        schema = get_schema(schema_type)
        if not schema:
            raise GraphBuilderError(f"Schema not found: {schema_type}")

        logger.info("Building graph with schema: %s", schema_type)

        # Use strategy registry instead of central if/elif dispatch

        strategy = get_strategy(
            schema_type,
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            mcp_tools_map=self.mcp_tools_map,
            memory_enabled=self.memory_enabled,
            checkpointer=self.checkpointer,
            repository=self.repository,
            gateway_tools=self.gateway_tools,
        )

        if strategy is None:
            raise GraphBuilderError(f"Unsupported schema type: {schema_type}")

        # Validate before building
        errors = strategy.validate(config)
        if errors:
            raise GraphBuilderError(f"Validation failed for {schema_type}: {', '.join(errors)}")

        return strategy.build(config)

    async def build_async(
        self, schema_type: str | GraphSchemaType, config: dict[str, Any] | None = None
    ) -> CompiledStateGraph | Pregel:
        """
        Build a graph from schema type and config, with support for sub_agent_ids from DB.

        Async version that can load referenced agents from database.

        Args:
            schema_type: Type of graph schema to build
            config: Configuration for the graph (can include sub_agent_ids)

        Returns:
            Compiled graph
        """
        config = config or {}

        if isinstance(schema_type, str):
            try:
                schema_type = GraphSchemaType(schema_type)
            except ValueError:
                raise GraphBuilderError(f"Unknown schema type: {schema_type}") from None

        schema = get_schema(schema_type)
        if not schema:
            raise GraphBuilderError(f"Schema not found: {schema_type}")

        logger.info("Building graph (async) with schema: %s", schema_type)

        # Use strategy registry instead of central if/elif dispatch

        strategy = get_strategy(
            schema_type,
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            mcp_tools_map=self.mcp_tools_map,
            memory_enabled=self.memory_enabled,
            checkpointer=self.checkpointer,
            repository=self.repository,
            gateway_tools=self.gateway_tools,
        )

        if strategy is None:
            raise GraphBuilderError(f"Unsupported schema type: {schema_type}")

        # Load sub-agents from DB if sub_agent_ids provided (for supervisor/pipeline)
        if schema_type in (GraphSchemaType.SUPERVISOR, GraphSchemaType.PIPELINE):
            target_field = "stages" if schema_type == GraphSchemaType.PIPELINE else "sub_agents"
            await self._load_sub_agents_from_db(config, target_field=target_field)

        # Validate before building
        errors = strategy.validate(config)
        if errors:
            raise GraphBuilderError(f"Validation failed for {schema_type}: {', '.join(errors)}")

        return await strategy.build(config)

    async def _load_sub_agents_from_db(
        self,
        config: dict[str, Any],
        *,
        target_field: str | None = None,
        _depth: int = 0,
    ) -> None:
        """
        Load sub-agents from DB and merge with config.

        If config has sub_agent_ids (list of UUIDs), load each agent's config
        and merge into sub_agents list.

        Args:
            config: Config dict to modify in-place

        ``_depth`` guards against a sub_agent_ids cycle (a supervisor whose
        chain of sub-agents loops back on itself, directly or indirectly) —
        this used to recurse with no bound at all until the stack gave out.
        """
        if not self.repository:
            logger.debug("No repository provided, skipping DB agent loading")
            return

        if _depth >= MAX_NESTED_SUB_AGENT_DEPTH:
            logger.warning(
                "Sub-agent nesting reached the %d-level depth limit, stopping",
                MAX_NESTED_SUB_AGENT_DEPTH,
            )
            return

        sub_agent_ids = config.get("sub_agent_ids", [])
        if not sub_agent_ids:
            logger.debug("No sub_agent_ids in config")
            return

        logger.info(f"Loading {len(sub_agent_ids)} sub-agents from DB")

        loaded_sub_agents = []

        for sub_id in sub_agent_ids:
            # Convert to UUID if string
            if isinstance(sub_id, str):
                try:
                    sub_id = UUID(sub_id)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid UUID: {sub_id}")
                    continue

            try:
                # Load sub-agent from repository, scoped to who may run it when
                # the caller told us (a client-supplied flow spec can name any id).
                if self.owner_ids is None:
                    sub_agent_def = await self.repository.get_by_id(sub_id)
                else:
                    sub_agent_def = await self.repository.get_by_id_for_user(sub_id, self.owner_ids)
                if not sub_agent_def:
                    logger.warning(f"Sub-agent {sub_id} not found or not available to the runner")
                    continue

                sub_config = agent_def_to_config(sub_agent_def)
                nested_target = (
                    "stages" if sub_config.get("graph_schema") == GraphSchemaType.PIPELINE.value else "sub_agents"
                )
                await self._load_sub_agents_from_db(
                    sub_config,
                    target_field=nested_target,
                    _depth=_depth + 1,
                )
                loaded_sub_agents.append(sub_config)

                logger.debug(f"Loaded sub-agent {sub_agent_def.name} (schema: {sub_agent_def.graph_schema})")

            except Exception as e:
                logger.error(f"Error loading sub-agent {sub_id}: {e}", exc_info=True)
                continue

        # Merge loaded agents with inline configs
        if loaded_sub_agents:
            field = target_field or (
                "stages" if config.get("graph_schema") == GraphSchemaType.PIPELINE.value else "sub_agents"
            )
            existing = config.get(field, [])
            config[field] = loaded_sub_agents + existing
            logger.info(f"Merged {len(loaded_sub_agents)} DB agents with {len(existing)} inline configs in {field}")


async def _inject_memory_context_async(messages: list, config: RunnableConfig) -> list:
    """Async memory context injection - safe to call from within async node functions."""
    try:
        configurable = config.get("configurable", {}) if config else {}
        user_id = configurable.get("user_id")
        long_term_memory = configurable.get("long_term_memory", False)

        if long_term_memory and user_id:
            store = configurable.get("store")
            if store:
                from memory.long_term import latest_human_message_text, recall_context_for_turn

                query = latest_human_message_text(messages)
                _, context = await recall_context_for_turn(user_id, query, configurable)
                if context:
                    return [SystemMessage(content=context), *list(messages)]
    except Exception as e:
        logger.warning(f"Memory injection failed: {e}")

    return messages


def build_graph(
    schema_type: str,
    config: dict[str, Any] | None = None,
    **builder_kwargs,
) -> CompiledStateGraph | Pregel:
    """
    Convenience function to build a graph.

    Args:
        schema_type: Type of graph schema
        config: Configuration for the graph
        **builder_kwargs: Additional arguments for GraphBuilder

    Returns:
        Compiled graph
    """
    builder = GraphBuilder(**builder_kwargs)
    return builder.build(schema_type, config)


def get_builder(**kwargs) -> GraphBuilder:
    """Get a GraphBuilder instance."""
    return GraphBuilder(**kwargs)
