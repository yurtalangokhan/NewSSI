"""Graph builder factory - builds LangGraph graphs from schema definitions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel

from agents.clarification.middleware import (
    AskUserAloneMiddleware,
    ask_user_alone_post_model_hook,
)
from agents.clarification.prompt import ASK_USER_PROMPT
from agents.clarification.tool import get_clarification_tools
from agents.document_tools import DOCUMENT_TOOL_PROMPT, get_document_tools
from agents.graphs.builder_helpers import agent_def_to_config
from agents.graphs.middleware import DeadEndTurnRetryMiddleware
from agents.graphs.schemas import (
    GraphSchemaType,
    get_schema,
)
from agents.mail_tooling import append_email_tool_policy, maybe_wrap_mcp_tool
from core.logger import get_logger

logger = get_logger(__name__)


class GraphBuilderError(Exception):
    """Error during graph building."""

    pass


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
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.mcp_tools_map = mcp_tools_map or {}
        self.memory_enabled = memory_enabled
        self.checkpointer = checkpointer
        self.repository = repository  # NEW: For loading sub-agents from DB
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
            from core import get_model

            return get_model(model_name)
        if self.model:
            return self.model
        from core import get_model, settings

        return get_model(settings.DEFAULT_MODEL)

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
                raise GraphBuilderError(f"Unknown schema type: {schema_type}")

        schema = get_schema(schema_type)
        if not schema:
            raise GraphBuilderError(f"Schema not found: {schema_type}")

        logger.info("Building graph with schema: %s", schema_type)

        # Use strategy registry instead of central if/elif dispatch
        from agents.graphs.strategies.registry import get_strategy

        strategy = get_strategy(
            schema_type,
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            mcp_tools_map=self.mcp_tools_map,
            memory_enabled=self.memory_enabled,
            checkpointer=self.checkpointer,
            repository=self.repository,
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
                raise GraphBuilderError(f"Unknown schema type: {schema_type}")

        schema = get_schema(schema_type)
        if not schema:
            raise GraphBuilderError(f"Schema not found: {schema_type}")

        logger.info("Building graph (async) with schema: %s", schema_type)

        # Use strategy registry instead of central if/elif dispatch
        from agents.graphs.strategies.registry import get_strategy

        strategy = get_strategy(
            schema_type,
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            mcp_tools_map=self.mcp_tools_map,
            memory_enabled=self.memory_enabled,
            checkpointer=self.checkpointer,
            repository=self.repository,
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
    ) -> None:
        """
        Load sub-agents from DB and merge with config.

        If config has sub_agent_ids (list of UUIDs), load each agent's config
        and merge into sub_agents list.

        Args:
            config: Config dict to modify in-place
        """
        if not self.repository:
            logger.debug("No repository provided, skipping DB agent loading")
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
                # Load sub-agent from repository
                sub_agent_def = await self.repository.get_by_id(sub_id)
                if not sub_agent_def:
                    logger.warning(f"Sub-agent {sub_id} not found in DB")
                    continue

                sub_config = agent_def_to_config(sub_agent_def)
                nested_target = (
                    "stages"
                    if sub_config.get("graph_schema") == GraphSchemaType.PIPELINE.value
                    else "sub_agents"
                )
                await self._load_sub_agents_from_db(
                    sub_config,
                    target_field=nested_target,
                )
                loaded_sub_agents.append(sub_config)

                logger.debug(
                    f"Loaded sub-agent {sub_agent_def.name} (schema: {sub_agent_def.graph_schema})"
                )

            except Exception as e:
                logger.error(f"Error loading sub-agent {sub_id}: {e}", exc_info=True)
                continue

        # Merge loaded agents with inline configs
        if loaded_sub_agents:
            field = target_field or (
                "stages"
                if config.get("graph_schema") == GraphSchemaType.PIPELINE.value
                else "sub_agents"
            )
            existing = config.get(field, [])
            config[field] = loaded_sub_agents + existing
            logger.info(
                f"Merged {len(loaded_sub_agents)} DB agents with "
                f"{len(existing)} inline configs in {field}"
            )

    def _attach_clarification(self, tools: list[Any], system_prompt: str) -> tuple[list[Any], str]:
        """Give a chat agent the ability to ask the user what they meant.

        Gated on the checkpointer, which decides two things at once:

        - Without one, ``interrupt()`` has nowhere to park and would return
          nothing at all, leaving the model with an empty answer to a question
          the user never saw (design 5.3, E13). A tool that does not exist
          cannot be called, so the situation never arises.
        - Every flow-canvas build constructs GraphBuilder with
          ``checkpointer=None`` (the parent flow owns persistence), so the tool
          stays out of flows for free (K3, E14). Flows have their own
          HumanInput node, and a RunFlow sub-run cannot pause at all.
        """
        if not self.checkpointer:
            return tools, system_prompt
        tools.extend(get_clarification_tools())
        return tools, f"{system_prompt}\n{ASK_USER_PROMPT}"

    def _clarification_post_model_hook(self):
        """The "call ask_user alone" guard for the ``create_react_agent`` paths.

        ``_build_react``/``_build_zero_shot`` run ``create_agent`` and get this
        guard as ``AskUserAloneMiddleware``. Sub-agents and plan-execute run
        ``create_react_agent``, which has no middleware slot — so they take the
        same guard as a ``post_model_hook``. Gated on the same checkpointer as
        the tool: no tool attached, no guard needed, so ``None`` (the
        create_react_agent default) is correct there.
        """
        return ask_user_alone_post_model_hook if self.checkpointer else None

    def _build_zero_shot(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build zero-shot chat graph.

        "Zero-shot" is one model call with a system prompt — a tool loop is what
        ReActAgent is for. Document tools alone used to trigger the upgrade
        below, which silently turned every zero-shot graph into a react agent
        (and appended DOCUMENT_TOOL_PROMPT to the caller's own prompt). An
        explicitly attached tool still upgrades, since that is the caller asking
        for a loop, but document tools never ride along into it.
        """
        tool_names = config.get("mcp_tools", [])
        extra_tools = config.get("extra_tools", []) or []
        if tool_names or extra_tools:
            return self._build_react({**config, "document_tools": False})

        from langgraph.graph import END, MessagesState, StateGraph

        system_prompt = config.get("system_prompt", self.system_prompt)
        model = self._get_model(config.get("model"))
        memory_enabled = self.memory_enabled

        async def call_model(state: MessagesState, config: RunnableConfig) -> MessagesState:
            messages = list(state["messages"])

            if memory_enabled:
                messages = await _inject_memory_context_async(messages, config)

            messages = [SystemMessage(content=system_prompt)] + messages
            response = await model.ainvoke(messages)
            return {"messages": [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("model", call_model)
        workflow.set_entry_point("model")
        workflow.add_edge("model", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _build_react(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build ReAct agent with tools."""
        tool_names = config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            config.get("system_prompt", self.system_prompt),
            tool_names,
            mail_attachments=config.get("mail_attachments"),
        )
        model = self._get_model(config.get("model"))

        tools = self._get_tools_for_names(
            tool_names,
            tool_configs=config.get("mcp_tool_configs") or {},
            user_id=config.get("user_id"),
            mail_attachments=config.get("mail_attachments"),
        )
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        # Prepend gateway tools so they take precedence over mcp_tools_map entries
        # with the same name (mcp_tools_map is consulted last).
        if self.gateway_tools:
            tools = list(self.gateway_tools) + tools

        document_tools = get_document_tools() if config.get("document_tools", True) else []
        if document_tools:
            tools.extend(document_tools)
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"

        tools, system_prompt = self._attach_clarification(tools, system_prompt)

        agent = create_agent(
            model=model,
            tools=tools,
            name="react-agent",
            system_prompt=system_prompt,
            checkpointer=self.checkpointer,
            middleware=[DeadEndTurnRetryMiddleware(), AskUserAloneMiddleware()],
        )

        return agent

    def _build_supervisor(self, config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build supervisor graph with sub-agents."""
        from langgraph_supervisor import create_supervisor

        supervisor_prompt = config.get("supervisor_prompt", "You are a team supervisor.")
        model = self._get_model(config.get("model"))

        sub_agents_config = config.get("sub_agents", [])
        if not sub_agents_config:
            logger.warning("No sub-agents configured for supervisor, using fallback")
            fallback_agent = create_react_agent(
                model=model,
                tools=[],
                name="fallback",
                prompt="You are a helpful assistant.",
            )
            workflow = create_supervisor(
                [fallback_agent],
                model=model,
                prompt="No sub-agents configured.",
                add_handoff_back_messages=True,
                output_mode="full_history",
            )
            return workflow.compile(checkpointer=self.checkpointer)

        agents_list = []
        agent_descriptions = []

        for sub_agent_cfg in sub_agents_config:
            if not isinstance(sub_agent_cfg, dict):
                continue

            name = sub_agent_cfg.get("name", "agent")
            sa_system_prompt = sub_agent_cfg.get("system_prompt", "You are a helpful agent.")
            tool_names = sub_agent_cfg.get("mcp_tools", [])
            if config.get("user_id") and not sub_agent_cfg.get("user_id"):
                sub_agent_cfg["user_id"] = config["user_id"]
            if config.get("mail_attachments") and not sub_agent_cfg.get("mail_attachments"):
                sub_agent_cfg["mail_attachments"] = config["mail_attachments"]
            agent = self._build_sub_agent_graph(sub_agent_cfg)

            agents_list.append(agent)
            tool_list = ", ".join(tool_names) if tool_names else "no tools"
            agent_descriptions.append(f"- {name}: {sa_system_prompt[:60]}... (tools: {tool_list})")

        enhanced_supervisor_prompt = (
            f"{supervisor_prompt}\n\nAvailable agents:\n"
            + "\n".join(agent_descriptions)
            + "\n\nDelegate tasks to the appropriate agent(s)."
        )

        workflow = create_supervisor(
            agents_list,
            model=model,
            prompt=enhanced_supervisor_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile(checkpointer=self.checkpointer, name=config.get("name"))

    def _build_pipeline(self, config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build pipeline graph with sequential stages."""
        from langgraph_supervisor import create_supervisor

        model = self._get_model(config.get("model"))
        pipeline_prompt = config.get("pipeline_prompt", "Process through all stages sequentially.")

        stages_config = config.get("stages", [])
        if not stages_config:
            logger.warning("No stages configured for pipeline, using fallback")
            fallback_agent = create_react_agent(
                model=model,
                tools=[],
                name="fallback",
                prompt="You are a helpful assistant.",
            )
            workflow = create_supervisor(
                [fallback_agent],
                model=model,
                prompt="No stages configured.",
                add_handoff_back_messages=True,
                output_mode="full_history",
            )
            return workflow.compile(checkpointer=self.checkpointer)

        agents_list = []
        stage_names = []

        for stage_cfg in stages_config:
            if not isinstance(stage_cfg, dict):
                continue

            name = stage_cfg.get("name", "stage")
            if config.get("user_id") and not stage_cfg.get("user_id"):
                stage_cfg["user_id"] = config["user_id"]
            if config.get("mail_attachments") and not stage_cfg.get("mail_attachments"):
                stage_cfg["mail_attachments"] = config["mail_attachments"]
            agent = self._build_sub_agent_graph(stage_cfg)

            agents_list.append(agent)
            stage_names.append(name)

        enhanced_prompt = (
            f"{pipeline_prompt}\n\nYou are a sequential pipeline."
            f" Process input through each stage in order.\nStages: {stage_names}"
        )

        workflow = create_supervisor(
            agents_list,
            model=model,
            prompt=enhanced_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile(checkpointer=self.checkpointer, name=config.get("name"))

    def _build_sub_agent_graph(self, agent_config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build a sub-agent graph, preserving nested manager schemas when configured."""
        schema_value = agent_config.get("graph_schema")
        try:
            schema_type = GraphSchemaType(schema_value) if schema_value else GraphSchemaType.REACT
        except ValueError:
            schema_type = GraphSchemaType.REACT

        if schema_type in (GraphSchemaType.SUPERVISOR, GraphSchemaType.PIPELINE):
            nested_builder = GraphBuilder(
                model=self._get_model(agent_config.get("model")),
                system_prompt=agent_config.get("system_prompt", self.system_prompt),
                tools=self.tools,
                mcp_tools_map=self.mcp_tools_map,
                memory_enabled=self.memory_enabled,
                checkpointer=self.checkpointer,
                repository=self.repository,
                gateway_tools=self.gateway_tools,
            )
            return nested_builder.build(schema_type, agent_config)

        name = agent_config.get("name", "agent")
        tool_names = agent_config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            agent_config.get("system_prompt", "You are a helpful agent."),
            tool_names,
            mail_attachments=agent_config.get("mail_attachments"),
        )
        agent_model = self._get_model(agent_config.get("model"))
        agent_tools = self._get_tools_for_names(
            tool_names,
            tool_configs=agent_config.get("mcp_tool_configs") or {},
            user_id=agent_config.get("user_id"),
            mail_attachments=agent_config.get("mail_attachments"),
        )

        # Prepend gateway tools so they take precedence.
        if self.gateway_tools:
            agent_tools = list(self.gateway_tools) + agent_tools

        document_tools = get_document_tools()
        if document_tools:
            agent_tools.extend(document_tools)
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"

        agent_tools, system_prompt = self._attach_clarification(agent_tools, system_prompt)

        return create_react_agent(
            model=agent_model,
            tools=agent_tools,
            name=name,
            prompt=SystemMessage(content=system_prompt),
            post_model_hook=self._clarification_post_model_hook(),
        )

    def _build_plan_execute(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build Plan & Execute graph."""
        tool_names = config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            config.get(
                "system_prompt",
                "First create a detailed plan, then execute each step methodically.",
            ),
            tool_names,
            mail_attachments=config.get("mail_attachments"),
        )
        model = self._get_model(config.get("model"))

        tools = self._get_tools_for_names(
            tool_names,
            tool_configs=config.get("mcp_tool_configs") or {},
            user_id=config.get("user_id"),
            mail_attachments=config.get("mail_attachments"),
        )
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        # Prepend gateway tools so they take precedence.
        if self.gateway_tools:
            tools = list(self.gateway_tools) + tools

        document_tools = get_document_tools()
        if document_tools:
            tools.extend(document_tools)
            system_prompt = f"{system_prompt}\n{DOCUMENT_TOOL_PROMPT}"

        tools, system_prompt = self._attach_clarification(tools, system_prompt)

        agent = create_react_agent(
            model=model,
            tools=tools,
            name="plan-execute",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=self.checkpointer,
            post_model_hook=self._clarification_post_model_hook(),
        )

        return agent

    def _build_self_reflect(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build Self-Reflect graph with generate → reflect loop."""
        from langgraph.graph import END, MessagesState, StateGraph

        system_prompt = config.get("system_prompt", self.system_prompt)
        reflection_prompt = config.get(
            "reflection_prompt",
            "Review this response and suggest improvements if needed. If it is already good, say 'DONE'.",
        )
        model = self._get_model(config.get("model"))
        max_iterations = int(config.get("max_iterations", 3))

        async def generate(state: MessagesState, config: RunnableConfig) -> MessagesState:
            messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
            response = await model.ainvoke(messages)
            return {"messages": [response]}

        async def reflect(state: MessagesState, config: RunnableConfig) -> MessagesState:
            last_msg = state["messages"][-1] if state["messages"] else None
            if not last_msg:
                return state

            reflection_query = f"{reflection_prompt}\n\nResponse to review:\n{last_msg.content}"
            reflection = await model.ainvoke([SystemMessage(content=reflection_query)])
            return {"messages": list(state["messages"]) + [reflection]}

        def should_continue(state: dict) -> str:
            # NOTE: intentionally annotated `dict`, not `MessagesState`. This
            # module uses `from __future__ import annotations`, so the hint is
            # a stringized forward ref; LangGraph's add_conditional_edges runs
            # get_type_hints() on this branch callable and resolves it against
            # this module's globals, where the function-local `MessagesState`
            # import is not visible -> NameError at build time.
            # Stop if max iterations reached or reflection says DONE
            msg_count = len(state["messages"])
            if msg_count >= max_iterations * 2 + 1:
                return "end"
            last_msg = state["messages"][-1] if state["messages"] else None
            if last_msg and "DONE" in str(last_msg.content).upper():
                return "end"
            return "reflect"

        workflow = StateGraph(MessagesState)
        workflow.add_node("generate", generate)
        workflow.add_node("reflect", reflect)
        workflow.set_entry_point("generate")
        workflow.add_conditional_edges(
            "generate", should_continue, {"reflect": "reflect", "end": END}
        )
        workflow.add_edge("reflect", "generate")

        return workflow.compile(checkpointer=self.checkpointer)


async def _inject_memory_context_async(messages: list, config: RunnableConfig) -> list:
    """Async memory context injection - safe to call from within async node functions."""
    try:
        configurable = config.get("configurable", {}) if config else {}
        user_id = configurable.get("user_id")
        long_term_memory = configurable.get("long_term_memory", False)

        if long_term_memory and user_id:
            store = configurable.get("store")
            if store:
                from memory.long_term import (
                    build_event_emitters,
                    build_memory_context,
                    recall_memories,
                )

                on_recall, _ = build_event_emitters(configurable)
                memories = await recall_memories(store, user_id, on_recall=on_recall)
                context = build_memory_context(memories)
                if context:
                    return [SystemMessage(content=context)] + list(messages)
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
