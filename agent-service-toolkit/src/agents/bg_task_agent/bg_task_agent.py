import asyncio

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda, RunnableSerializable
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import StreamWriter

from agents.bg_task_agent.task import Task
from core import get_model, settings
from memory.long_term import (
    build_memory_context,
    extract_and_save_memories,
    recall_memories,
)


class AgentState(MessagesState, total=False):
    """`total=False` is PEP589 specs.

    documentation: https://typing.readthedocs.io/en/latest/spec/typeddict.html#totality
    """


def wrap_model(model: BaseChatModel) -> RunnableSerializable[AgentState, AIMessage]:
    preprocessor = RunnableLambda(
        lambda state: state["messages"],
        name="StateModifier",
    )
    return preprocessor | model  # type: ignore[return-value]


async def acall_model(state: AgentState, config: RunnableConfig, *, store: BaseStore) -> AgentState:
    configurable = config.get("configurable", {})
    m = get_model(configurable.get("model", settings.DEFAULT_MODEL))

    # Long-term memory: recall user facts if enabled
    long_term_memory = configurable.get("long_term_memory", False)
    user_id = configurable.get("user_id")
    memories: dict = {}

    if long_term_memory and store and user_id:
        memories = await recall_memories(store, user_id)
        memory_context = build_memory_context(memories)
        if memory_context:
            preprocessor = RunnableLambda(
                lambda state, mc=memory_context: [SystemMessage(content=mc)] + state["messages"],
                name="StateModifier",
            )
            model_runnable = preprocessor | m
        else:
            model_runnable = wrap_model(m)
    else:
        model_runnable = wrap_model(m)

    response = await model_runnable.ainvoke(state, config)

    # Long-term memory: extract and save new facts
    if long_term_memory and store and user_id:
        await extract_and_save_memories(
            store, user_id, list(state["messages"]) + [response], m, memories
        )

    # We return a list, because this will get added to the existing list
    return {"messages": [response]}


async def bg_task(state: AgentState, writer: StreamWriter, config: RunnableConfig) -> AgentState:
    configurable = config.get("configurable", {})
    max_retries = configurable.get("max_retries", 3)
    timeout = configurable.get("timeout_seconds", 3600)
    
    task1 = Task(f"Index Repo (Retries: {max_retries})", writer)
    task2 = Task(f"Vector DB Sync (Timeout: {timeout}s)", writer)

    task1.start()
    await asyncio.sleep(2)
    task2.start()
    await asyncio.sleep(2)
    task1.write_data(data={"status": "Still running..."})
    await asyncio.sleep(2)
    task2.finish(result="error", data={"output": 42})
    await asyncio.sleep(2)
    task1.finish(result="success", data={"output": 42})
    return {"messages": []}


# Define the graph
agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("bg_task", bg_task)
agent.set_entry_point("bg_task")

agent.add_edge("bg_task", "model")
agent.add_edge("model", END)

bg_task_agent = agent.compile()
