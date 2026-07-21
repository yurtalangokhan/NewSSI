"""Graph builder factory - builds LangGraph graphs from schema definitions."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel

from agents.graphs.schemas import (
    GraphSchemaType,
    get_schema,
)

logger = logging.getLogger(__name__)


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
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.mcp_tools_map = mcp_tools_map or {}
        self.memory_enabled = memory_enabled
        self.checkpointer = checkpointer
        self.repository = repository  # NEW: For loading sub-agents from DB

    def _get_tools_for_names(self, tool_names: list[str]) -> list[Any]:
        """Get tool instances from names using the tools map."""
        tools = []
        for name in tool_names:
            if name in self.mcp_tools_map:
                tools.append(self.mcp_tools_map[name])
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

        if schema_type == GraphSchemaType.ZERO_SHOT:
            return self._build_zero_shot(config)
        elif schema_type == GraphSchemaType.REACT:
            return self._build_react(config)
        elif schema_type == GraphSchemaType.SUPERVISOR:
            return self._build_supervisor(config)
        elif schema_type == GraphSchemaType.PIPELINE:
            return self._build_pipeline(config)
        elif schema_type == GraphSchemaType.PLAN_EXECUTE:
            return self._build_plan_execute(config)
        elif schema_type == GraphSchemaType.SELF_REFLECT:
            return self._build_self_reflect(config)
        else:
            raise GraphBuilderError(f"Unsupported schema type: {schema_type}")

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

        # NEW: Load sub-agents from DB if sub_agent_ids provided
        if schema_type in (GraphSchemaType.SUPERVISOR, GraphSchemaType.PIPELINE):
            target_field = "stages" if schema_type == GraphSchemaType.PIPELINE else "sub_agents"
            await self._load_sub_agents_from_db(config, target_field=target_field)

        # Delegate to existing schema-specific builders
        if schema_type == GraphSchemaType.ZERO_SHOT:
            return self._build_zero_shot(config)
        elif schema_type == GraphSchemaType.REACT:
            return self._build_react(config)
        elif schema_type == GraphSchemaType.SUPERVISOR:
            return self._build_supervisor(config)
        elif schema_type == GraphSchemaType.PIPELINE:
            return self._build_pipeline(config)
        elif schema_type == GraphSchemaType.PLAN_EXECUTE:
            return self._build_plan_execute(config)
        elif schema_type == GraphSchemaType.SELF_REFLECT:
            return self._build_self_reflect(config)
        else:
            raise GraphBuilderError(f"Unsupported schema type: {schema_type}")

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

                sub_config = self._agent_def_to_config(sub_agent_def)
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
                    f"Loaded sub-agent {sub_agent_def.name} (schema: "
                    f"{sub_agent_def.graph_schema})"
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

    def _agent_def_to_config(self, agent_def: Any) -> dict[str, Any]:
        """
        Convert AgentDefinitionModel to graph config dict.

        Args:
            agent_def: AgentDefinitionModel instance

        Returns:
            Config dict compatible with graph builders
        """
        return {
            "name": agent_def.name,
            "graph_schema": agent_def.graph_schema,
            "system_prompt": agent_def.system_prompt or "You are a helpful agent.",
            "model": agent_def.model,
            "mcp_tools": agent_def.mcp_tools or [],
            "rag_config": agent_def.rag_config,
            "supervisor_prompt": agent_def.supervisor_prompt,
            "stages": agent_def.stages,
            "pipeline_prompt": agent_def.pipeline_prompt,
            "reflection_prompt": agent_def.reflection_prompt,
            "max_iterations": agent_def.max_iterations or 3,
            "sub_agent_ids": agent_def.sub_agent_ids or [],
        }

    def _build_zero_shot(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build zero-shot chat graph."""
        tool_names = config.get("mcp_tools", [])
        extra_tools = config.get("extra_tools", []) or []
        if tool_names or extra_tools:
            return self._build_react(config)

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
        system_prompt = config.get("system_prompt", self.system_prompt)
        model = self._get_model(config.get("model"))

        tool_names = config.get("mcp_tools", [])
        tools = self._get_tools_for_names(tool_names)
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        agent = create_react_agent(
            model=model,
            tools=tools,
            name="react-agent",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=self.checkpointer,
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
            )
            return nested_builder.build(schema_type, agent_config)

        name = agent_config.get("name", "agent")
        system_prompt = agent_config.get("system_prompt", "You are a helpful agent.")
        tool_names = agent_config.get("mcp_tools", [])
        agent_model = self._get_model(agent_config.get("model"))
        agent_tools = self._get_tools_for_names(tool_names)

        return create_react_agent(
            model=agent_model,
            tools=agent_tools,
            name=name,
            prompt=SystemMessage(content=system_prompt),
        )

    def _build_plan_execute(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build Plan & Execute graph."""
        system_prompt = config.get(
            "system_prompt",
            "First create a detailed plan, then execute each step methodically.",
        )
        model = self._get_model(config.get("model"))

        tool_names = config.get("mcp_tools", [])
        tools = self._get_tools_for_names(tool_names)
        extra_tools = config.get("extra_tools", []) or []
        tools.extend(extra_tools)

        agent = create_react_agent(
            model=model,
            tools=tools,
            name="plan-execute",
            prompt=SystemMessage(content=system_prompt),
            checkpointer=self.checkpointer,
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

        def should_continue(state: MessagesState) -> str:
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
