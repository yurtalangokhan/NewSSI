from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore

from agents.document_tools import DOCUMENT_TOOL_PROMPT, bind_document_tools, get_document_tools
from core import settings
from core.llm import get_model_from_config
from core.logger import get_logger
from memory.long_term import (
    build_event_emitters,
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
    tag_response_with_ltm_recall,
)

logger = get_logger(__name__)

# Bounded so a model that keeps emitting tool_calls can't loop forever.
_MAX_DOCUMENT_TOOL_ITERATIONS = 4


async def _run_with_document_tools(
    model,
    messages: list,
    config: RunnableConfig,
) -> list:
    """Run a bounded tool-calling loop restricted to the document output tools.

    Returns every new message produced (tool-call AIMessages, ToolMessages,
    and the final answer) so the caller can persist them all onto the graph
    state — matching how react-based agents expose tool steps natively.
    """
    document_tools = get_document_tools()
    if not document_tools:
        response = await model.ainvoke(messages)
        return [response]

    bound_model, tools_enabled = bind_document_tools(model, document_tools)
    if not tools_enabled:
        response = await model.ainvoke(messages)
        return [response]

    tools_by_name = {tool.name: tool for tool in document_tools}
    conversation = [SystemMessage(content=DOCUMENT_TOOL_PROMPT), *messages]
    new_messages: list = []

    for _ in range(_MAX_DOCUMENT_TOOL_ITERATIONS):
        ai_message = await bound_model.ainvoke(conversation)
        conversation.append(ai_message)
        new_messages.append(ai_message)

        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if not tool_calls:
            break

        for call in tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                tool_message = ToolMessage(
                    content=f"Error: unknown tool '{call['name']}'.",
                    tool_call_id=call["id"],
                )
            else:
                result = await tool.ainvoke(call["args"], config)
                tool_message = ToolMessage(content=str(result), tool_call_id=call["id"])
            conversation.append(tool_message)
            new_messages.append(tool_message)

    return new_messages


async def call_model(
    state: MessagesState, config: RunnableConfig, *, store: BaseStore
) -> MessagesState:
    messages = state["messages"]
    configurable = config.get("configurable", {})
    model = get_model_from_config(configurable, settings.DEFAULT_MODEL)

    # Long-term memory: recall user facts if enabled
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}
    on_recall, on_save = build_event_emitters(configurable)

    logger.debug(
        "long_term_memory=%s, user_id=%s, store=%s, store_type=%s",
        long_term_memory,
        user_id,
        store is not None,
        type(store).__name__ if store else "None",
    )

    if long_term_memory and user_id:
        try:
            memories = await recall_memories(store, user_id, on_recall=on_recall)
            logger.debug("Recalled memories: %s", memories)
            memory_context = build_memory_context(memories)
            if memory_context:
                messages = [SystemMessage(content=memory_context)] + list(messages)
                logger.debug("Injected memory context into messages")
            else:
                logger.debug("No memory context to inject (empty)")
        except Exception as e:
            logger.error("ERROR during recall: %s", e)
    else:
        logger.debug(
            "Skipping memory: long_term_memory=%s, store=%s, user_id=%s",
            long_term_memory,
            store is not None,
            user_id,
        )

    system_prompt = configurable.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt.strip():
        messages = [SystemMessage(content=system_prompt.strip())] + list(messages)

    new_messages = await _run_with_document_tools(model, messages, config)
    response = new_messages[-1]
    tag_response_with_ltm_recall(response, memories)

    # Long-term memory: extract and save new facts
    if long_term_memory and user_id:
        try:
            extract_mem = configurable.get("extract_memory", True)
            await extract_and_save_memories(
                store,
                user_id,
                list(state["messages"]) + new_messages,
                model,
                memories,
                on_save=on_save,
                extract_memory=extract_mem,
            )
            logger.debug("Memory extraction completed")
        except Exception as e:
            logger.error("ERROR during extraction: %s", e)

    return {"messages": new_messages}


workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.set_entry_point("model")
workflow.add_edge("model", END)

chatbot = workflow.compile()
