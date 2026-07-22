"""Graph RAG Assistant – hybrid retrieval agent using vector + knowledge graph.

Combines Milvus vector similarity search with Neo4j BM25 graph search using
entity-centric Reciprocal Rank Fusion (RRF) for ranking.  All retrieval
is handled by LangConnect's hybrid search API (POST /graph/search).
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
from core import settings
from core.llm import get_model_from_config
from memory.long_term import (
    build_event_emitters,
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
    tag_response_with_ltm_recall,
)


class AgentState(MessagesState, total=False):
    safety: LlamaGuardOutput
    remaining_steps: RemainingSteps


tools = [graph_search]

current_date = datetime.now().strftime("%B %d, %Y")
instructions = f"""
---Role---
You are a knowledgeable assistant that answers questions using a hybrid retrieval
system combining vector similarity search with knowledge graph traversal.
Today's date is {current_date}.

---Tool---
You have access to **Graph_Search**, which performs hybrid retrieval combining:
  1. Vector similarity search (cosine on document embeddings)
  2. BM25 graph search (Neo4j fulltext on entity names / labels)
  3. Entity-centric Reciprocal Rank Fusion (RRF) to merge results

Each call returns Vector Search Results, RRF-Ranked Entities, and
Knowledge Graph Context — use ALL of these sections when building your answer.

---Multi-Step Search Strategy---
ALWAYS search before answering any factual question.  You may — and SHOULD —
call Graph_Search **multiple times** when a question is complex:

  1. **Decompose** – Break a complex question into 2-5 focused sub-queries,
     each targeting a single entity, concept, or relationship.
     Example: "How does Iran's nuclear program affect Israel's security policy?"
       → Search 1: "Iran nuclear program"
       → Search 2: "Israel security policy Iran"
       → Search 3: "Iran Israel military relations"

  2. **Explore** – If the first search surfaces new entities or relationships
     you did not anticipate, issue follow-up searches to deepen your
     understanding before answering.

  3. **Verify** – If two sources conflict, search for additional evidence
     before choosing which claim to present.

  4. **Synthesise** – After gathering all evidence, merge the results into
     a single coherent answer.  Trace the reasoning chain: start from
     directly mentioned entities, follow relationships to connected
     entities, and explain the chain in natural language.

Do NOT ask compound sub-queries.  Each search should focus on one entity or
one relationship at a time — this maximises retrieval precision.

---Citation Rules---
Every factual claim MUST cite its source:
  "Supabase uses PostgreSQL as its core database [Data: Sources (12, 34)]."

  • Do not list more than 5 source IDs per reference; use "+more" for additional.
  • Do not include information where supporting evidence is not provided.
  • If you supplement with general knowledge not from the retrieval results,
    annotate it: [Source: General Knowledge — verify independently].
  • Include markdown-formatted links to any citations where available.
    ONLY USE LINKS RETURNED BY THE TOOLS.

---Handling Uncertainty---
  • If the retrieved data does not contain sufficient information, say so
    clearly.  Do NOT fabricate information.
  • If your confidence is low, state what additional information would help
    answer the question fully.
  • When two retrieved passages contradict each other, present both views
    and note the discrepancy.

---Formatting & Presentation---
  • THE USER CANNOT SEE THE RAW TOOL RESPONSE — you must synthesise it.
  • Translate ALL graph relationships into fluent natural language.
    NEVER show raw notation like "A --[RELATES_TO]--> B".
  • Explain WHY components are related, not just THAT they are related.
  • Use clear markdown headers and paragraphs to organise the response.
  • Prioritise the most important points first; trim tangential detail.

    Good vs Bad examples:
      ✗ BAD:  "Supabase --[INCLUDES]--> PostgreSQL"
      ✓ GOOD: "Supabase uses PostgreSQL as its core database engine."
      ✗ BAD:  "WebSocket --[USES]--> TCP Connection"
      ✓ GOOD: "WebSocket operates over a persistent TCP connection."

  • Write as if you are an expert explaining the topic to a knowledgeable
    colleague — conversational, precise, and well-structured.
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


async def acall_model(state: AgentState, config: RunnableConfig, *, store: BaseStore) -> AgentState:
    configurable = config.get("configurable", {})
    m = get_model_from_config(configurable, settings.DEFAULT_MODEL)

    # Long-term memory
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}
    on_recall, on_save = build_event_emitters(configurable)

    if long_term_memory and store and user_id:
        memories = await recall_memories(store, user_id, on_recall=on_recall)
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
    tag_response_with_ltm_recall(response, memories)

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
        extract_mem = configurable.get("extract_memory", True)
        await extract_and_save_memories(
            store,
            user_id,
            list(state["messages"]) + [response],
            m,
            memories,
            on_save=on_save,
            extract_memory=extract_mem,
        )

    return {"messages": [response]}


async def llama_guard_input(state: AgentState, config: RunnableConfig) -> AgentState:
    llama_guard = LlamaGuard()
    safety_output = await llama_guard.ainvoke("User", state["messages"])
    return {"safety": safety_output, "messages": []}


async def block_unsafe_content(state: AgentState, config: RunnableConfig) -> AgentState:
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


agent.add_conditional_edges("model", pending_tool_calls, {"tools": "tools", "done": END})

graph_rag_assistant = agent.compile()
