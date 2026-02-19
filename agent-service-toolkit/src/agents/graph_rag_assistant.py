"""Graph RAG Assistant – hybrid retrieval agent using vector + knowledge graph.

Combines PGVector similarity search with Neo4j graph traversal using
Reciprocal Rank Fusion (RRF) for ranking. Uses both `database_search`
(vector) and `graph_search` (Neo4j) tools.
"""

from datetime import datetime
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import (
    RunnableConfig,
    RunnableLambda,
    RunnableSerializable,
)
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.managed import RemainingSteps
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from agents.llama_guard import LlamaGuard, LlamaGuardOutput, SafetyAssessment
from agents.tools import graph_search
from core import get_model, settings
from memory.long_term import (
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
)


class AgentState(MessagesState, total=False):
    safety: LlamaGuardOutput
    remaining_steps: RemainingSteps


tools = [graph_search]

current_date = datetime.now().strftime("%B %d, %Y")
instructions = f"""
    You are a highly knowledgeable virtual assistant powered by a hybrid retrieval system
    that combines traditional vector search with a knowledge graph for enhanced accuracy.
    Today's date is {current_date}.

    You have access to the following search tool:
    - **Graph_Search** – performs hybrid retrieval by combining vector similarity search
      (cosine similarity on document embeddings) with knowledge graph traversal (Neo4j
      entity and relationship search), then fuses results using Reciprocal Rank Fusion (RRF).
      This gives you both relevant text passages AND entity/relationship context in a single call.

    Strategy for answering questions:
    - ALWAYS use Graph_Search for every user question that requires information lookup.
    - Graph_Search automatically combines vector search and graph search results.
    - For questions about relationships, connections, or entities, the graph context
      in the results will be especially useful.
    - Always cite information from the tool. Do not make up information.

    NOTE: THE USER CAN'T SEE THE TOOL RESPONSE.

    A few things to remember:
    - Please include markdown-formatted links to any citations used in your response.
    - Only use information from the tool. Do not use information from outside sources.
    - When the graph provides entity relationships, explain them clearly to the user.
    """


def wrap_model(model: BaseChatModel) -> RunnableSerializable[AgentState, AIMessage]:
    bound_model = model.bind_tools(tools)
    preprocessor = RunnableLambda(
        lambda state: [SystemMessage(content=instructions)] + state["messages"],
        name="StateModifier",
    )
    return preprocessor | bound_model


def format_safety_message(safety: LlamaGuardOutput) -> AIMessage:
    content = (
        f"This conversation was flagged for unsafe content: {', '.join(safety.unsafe_categories)}"
    )
    return AIMessage(content=content)


async def acall_model(
    state: AgentState, config: RunnableConfig, *, store: BaseStore
) -> AgentState:
    configurable = config.get("configurable", {})
    m = get_model(configurable.get("model", settings.DEFAULT_MODEL))

    # Long-term memory
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}

    if long_term_memory and store and user_id:
        memories = await recall_memories(store, user_id)
        memory_context = build_memory_context(memories)
        if memory_context:
            enhanced_instructions = instructions + memory_context
            bound_model = m.bind_tools(tools)
            preprocessor = RunnableLambda(
                lambda state, ei=enhanced_instructions: [SystemMessage(content=ei)]
                + state["messages"],
                name="StateModifier",
            )
            model_runnable = preprocessor | bound_model
        else:
            model_runnable = wrap_model(m)
    else:
        model_runnable = wrap_model(m)

    response = await model_runnable.ainvoke(state, config)

    # LlamaGuard safety check
    llama_guard = LlamaGuard()
    safety_output = await llama_guard.ainvoke("Agent", state["messages"] + [response])
    if safety_output.safety_assessment == SafetyAssessment.UNSAFE:
        return {
            "messages": [format_safety_message(safety_output)],
            "safety": safety_output,
        }

    if state["remaining_steps"] < 2 and response.tool_calls:
        return {
            "messages": [
                AIMessage(
                    id=response.id,
                    content="Sorry, need more steps to process this request.",
                )
            ]
        }

    # Long-term memory: extract and save
    if long_term_memory and store and user_id:
        await extract_and_save_memories(
            store, user_id, list(state["messages"]) + [response], m, memories
        )

    return {"messages": [response]}


async def llama_guard_input(
    state: AgentState, config: RunnableConfig
) -> AgentState:
    llama_guard = LlamaGuard()
    safety_output = await llama_guard.ainvoke("User", state["messages"])
    return {"safety": safety_output, "messages": []}


async def block_unsafe_content(
    state: AgentState, config: RunnableConfig
) -> AgentState:
    safety: LlamaGuardOutput = state["safety"]
    return {"messages": [format_safety_message(safety)]}


# Build the graph
agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))
agent.add_node("guard_input", llama_guard_input)
agent.add_node("block_unsafe_content", block_unsafe_content)
agent.set_entry_point("guard_input")


def check_safety(state: AgentState) -> Literal["unsafe", "safe"]:
    safety: LlamaGuardOutput = state["safety"]
    match safety.safety_assessment:
        case SafetyAssessment.UNSAFE:
            return "unsafe"
        case _:
            return "safe"


agent.add_conditional_edges(
    "guard_input", check_safety, {"unsafe": "block_unsafe_content", "safe": "model"}
)
agent.add_edge("block_unsafe_content", END)
agent.add_edge("tools", "model")


def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage):
        raise TypeError(f"Expected AIMessage, got {type(last_message)}")
    if last_message.tool_calls:
        return "tools"
    return "done"


agent.add_conditional_edges(
    "model", pending_tool_calls, {"tools": "tools", "done": END}
)

graph_rag_assistant = agent.compile()
