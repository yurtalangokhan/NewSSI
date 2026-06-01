from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore

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

    response = await model.ainvoke(messages)
    tag_response_with_ltm_recall(response, memories)

    # Long-term memory: extract and save new facts
    if long_term_memory and user_id:
        try:
            extract_mem = configurable.get("extract_memory", True)
            await extract_and_save_memories(
                    store, user_id, list(state["messages"]) + [response], model, memories,
                    on_save=on_save, extract_memory=extract_mem
            )
            logger.debug("Memory extraction completed")
        except Exception as e:
            logger.error("ERROR during extraction: %s", e)

    return {"messages": [response]}


workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.set_entry_point("model")
workflow.add_edge("model", END)

chatbot = workflow.compile()
