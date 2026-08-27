"""Zero-shot graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class ZeroShotGraphStrategy(GraphSchemaStrategy):
    """Strategy for zero-shot chat - simple model call with system prompt."""

    schema_type = GraphSchemaType.ZERO_SHOT

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """Zero-shot requires only a system prompt (has default)."""
        return ()  # No required fields, all have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build zero-shot chat graph."""
        from langgraph.graph import END
        from langgraph.graph.state import MessagesState, StateGraph

        tool_names = config.get("mcp_tools", [])
        extra_tools = config.get("extra_tools", []) or []

        # Zero-shot with tools falls back to react
        if tool_names or extra_tools or self._get_document_tools():
            from agents.graphs.strategies.react import ReActGraphStrategy

            react_strategy = ReActGraphStrategy(
                model=self.model,
                system_prompt=config.get("system_prompt", self.system_prompt),
                tools=self.tools,
                mcp_tools_map=self.mcp_tools_map,
                memory_enabled=self.memory_enabled,
                checkpointer=self.checkpointer,
                repository=self.repository,
            )
            return await react_strategy.build(config)

        system_prompt = config.get("system_prompt", self.system_prompt)
        model = self._get_model(config.get("model"))
        memory_enabled = self.memory_enabled

        async def call_model(state: MessagesState, config: RunnableConfig) -> MessagesState:
            from agents.graphs.builder import _inject_memory_context_async

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
