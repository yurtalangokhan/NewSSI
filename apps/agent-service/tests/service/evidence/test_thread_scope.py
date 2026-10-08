"""current_thread_id: the chat thread a tool call runs in, from the LangGraph config."""

from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from service.knowledge_evidence.thread_scope import current_thread_id

from .conftest import THREAD_ID


def test_reads_the_thread_id_of_the_running_graph() -> None:
    probe = RunnableLambda(lambda _: current_thread_id())

    assert probe.invoke(None, config={"configurable": {"thread_id": str(THREAD_ID)}}) == THREAD_ID


def test_non_uuid_thread_id_is_ignored() -> None:
    probe = RunnableLambda(lambda _: current_thread_id())

    assert probe.invoke(None, config={"configurable": {"thread_id": "playground"}}) is None


def test_outside_a_runnable_there_is_no_thread() -> None:
    assert current_thread_id() is None
