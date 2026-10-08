"""Zero-shot graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from agents.graphs.strategies.base import GraphSchemaStrategy
from schemas.agent_graphs import GraphSchemaType

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class ZeroShotGraphStrategy(GraphSchemaStrategy):
    """Strategy for zero-shot chat - simple model call with system prompt."""

    schema_type = GraphSchemaType.ZERO_SHOT

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:  # noqa: ARG002
        """Zero-shot requires only a system prompt (has default)."""
        return ()  # No required fields, all have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build zero-shot chat graph."""
        from langgraph.graph import END, MessagesState
        from langgraph.graph.state import StateGraph

        tool_names = config.get("mcp_tools", [])
        extra_tools = config.get("extra_tools", []) or []

        # An explicitly attached tool -- a selected mcp_tools name, an
        # extra_tool, or a built-in gateway tool -- is the caller asking for
        # a tool loop, so zero-shot upgrades to react for it.
        #
        # Document tools are deliberately not in that list. They are always
        # on, so upgrading for them would mean every zero-shot graph is
        # really a react agent: a component documented as "a single model
        # call with a system prompt, no tools" would call tools, and the
        # caller's prompt would be silently extended with
        # DOCUMENT_TOOL_PROMPT. They are also kept out of the upgrade it
        # does perform, via document_tools=False.
        if tool_names or extra_tools or self.gateway_tools:
            from agents.graphs.strategies.react import ReActGraphStrategy

            react_strategy = ReActGraphStrategy(
                model=self.model,
                system_prompt=config.get("system_prompt", self.system_prompt),
                tools=self.tools,
                mcp_tools_map=self.mcp_tools_map,
                memory_enabled=self.memory_enabled,
                checkpointer=self.checkpointer,
                repository=self.repository,
                gateway_tools=self.gateway_tools,
            )
            return await react_strategy.build({**config, "document_tools": False})

        system_prompt = config.get("system_prompt", self.system_prompt)
        model = await self._get_model(config.get("model"))
        memory_enabled = self.memory_enabled

        async def call_model(state: MessagesState, config: RunnableConfig) -> MessagesState:
            from agents.graphs.builder_helpers import _inject_memory_context_async

            messages = list(state["messages"])

            if memory_enabled:
                messages = await _inject_memory_context_async(messages, config)

            messages = [SystemMessage(content=system_prompt), *messages]
            response = await model.ainvoke(messages)
            return {"messages": [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("model", call_model)
        workflow.set_entry_point("model")
        workflow.add_edge("model", END)

        return workflow.compile(checkpointer=self.checkpointer)
