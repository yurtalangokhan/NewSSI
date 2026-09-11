"""Self-reflect graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

# Imported at module scope on purpose: LangGraph resolves the node callables'
# annotations at runtime (``get_type_hints``), and with
# ``from __future__ import annotations`` a TYPE_CHECKING-only import leaves
# ``MessagesState`` undefined there.
from langgraph.graph import MessagesState

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


class SelfReflectGraphStrategy(GraphSchemaStrategy):
    """Strategy for Self-Reflect - agent with self-correction loop."""

    schema_type = GraphSchemaType.SELF_REFLECT

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """SelfReflect has no required fields (all have defaults)."""
        return ()  # All fields have defaults

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph:
        """Build Self-Reflect graph with generate → reflect loop."""
        from langgraph.graph import END
        from langgraph.graph.state import StateGraph

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
