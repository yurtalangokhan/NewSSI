from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore

from core import get_model, settings
from memory.long_term import (
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
)


async def call_model(state: MessagesState, config: RunnableConfig, *, store: BaseStore) -> MessagesState:
    messages = state["messages"]
    configurable = config.get("configurable", {})
    model = get_model(configurable.get("model", settings.DEFAULT_MODEL))

    # Long-term memory: recall user facts if enabled
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}

    print(f"[CHATBOT_MEMORY] long_term_memory={long_term_memory}, user_id={user_id}, store={store is not None}, store_type={type(store).__name__ if store else 'None'}")

    if long_term_memory and store and user_id:
        try:
            memories = await recall_memories(store, user_id)
            print(f"[CHATBOT_MEMORY] Recalled memories: {memories}")
            memory_context = build_memory_context(memories)
            if memory_context:
                messages = [SystemMessage(content=memory_context)] + list(messages)
                print("[CHATBOT_MEMORY] Injected memory context into messages")
            else:
                print("[CHATBOT_MEMORY] No memory context to inject (empty)")
        except Exception as e:
            print(f"[CHATBOT_MEMORY] ERROR during recall: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[CHATBOT_MEMORY] Skipping memory: long_term_memory={long_term_memory}, store={store is not None}, user_id={user_id}")

    response = await model.ainvoke(messages)

    # Long-term memory: extract and save new facts
    if long_term_memory and store and user_id:
        try:
            print("[CHATBOT_MEMORY] Starting memory extraction...")
            await extract_and_save_memories(
                store, user_id, list(state["messages"]) + [response], model, memories
            )
            print("[CHATBOT_MEMORY] Memory extraction completed")
        except Exception as e:
            print(f"[CHATBOT_MEMORY] ERROR during extraction: {e}")
            import traceback
            traceback.print_exc()

    return {"messages": [response]}


workflow = StateGraph(MessagesState)
workflow.add_node("model", call_model)
workflow.set_entry_point("model")
workflow.add_edge("model", END)

chatbot = workflow.compile()
