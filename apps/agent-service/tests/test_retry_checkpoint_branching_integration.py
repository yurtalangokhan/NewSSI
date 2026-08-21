"""End-to-end integration test for retry checkpoint branching (Task 6 of
.tmp/2026-08-21-retry-checkpoint-branching-plan.md), using a REAL LangGraph
graph + InMemorySaver (no Postgres needed) instead of mocks — this is the
one test in the whole plan that exercises _handle_input,
CheckpointBranchService, ThreadController.get_thread_state_history, and
reconstruct_message_tree together, wired exactly as the real agent
invocation path wires them.
"""

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import MessagesState, StateGraph

from controller.thread_controller import ThreadController
from service.ChatHistoryReconstruction import reconstruct_message_tree
from service.CheckpointBranchService import find_fork_point
from service.CheckpointerService import set_global_checkpointer


class _RecordingModelNode:
    """Returns a scripted response per call and records what messages it
    actually saw — this is how we verify a forked retry's model call never
    sees the rejected response."""

    def __init__(self):
        self.responses = iter(["ilk cevap", "retry cevabı"])
        self.seen_message_contents: list[list[str]] = []

    async def __call__(self, state: MessagesState):
        self.seen_message_contents.append(
            [getattr(m, "content", "") for m in state["messages"]]
        )
        return {"messages": [AIMessage(content=next(self.responses))]}


@pytest_asyncio.fixture
async def compiled_graph():
    from service import CheckpointerService

    previous_checkpointer = CheckpointerService.get_checkpointer()

    node = _RecordingModelNode()
    workflow = StateGraph(MessagesState)
    workflow.add_node("model", node)
    workflow.set_entry_point("model")
    saver = InMemorySaver()
    graph = workflow.compile(checkpointer=saver)
    # ThreadController.get_thread_state_history reads the global checkpointer
    # singleton, so it must point at this test's saver for the real
    # end-to-end pipeline to line up.
    set_global_checkpointer(saver)
    try:
        yield graph, node
    finally:
        set_global_checkpointer(previous_checkpointer)


@pytest.mark.asyncio
async def test_retry_forks_the_checkpoint_and_never_sees_the_rejected_response(
    compiled_graph,
):
    graph, node = compiled_graph
    thread_id = "integration-thread-1"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: a normal send.
    result = await graph.ainvoke({"messages": [("human", "soru")]}, config=config)
    assert result["messages"][-1].content == "ilk cevap"

    # Locate the fork point for the human message we're about to retry —
    # exactly what AgentHelpers._handle_input does when is_regenerate=True.
    thread_controller = ThreadController()
    target_message_id = 1  # the human message reconstruct_messages assigns id 1 to

    fork_config = await find_fork_point(
        graph,
        thread_id=thread_id,
        target_message_id=target_message_id,
        thread_metadata={"persona_id": 0},
    )
    assert fork_config is not None, "fork point must resolve for a real single-turn thread"

    # Invoke the retry from the forked checkpoint with NO new human message —
    # exactly what AgentHelpers._handle_input does (input=None) once forking
    # succeeds.
    retry_config = {**config, "configurable": {**config["configurable"], **fork_config["configurable"]}}
    retry_result = await graph.ainvoke(None, config=retry_config)
    assert retry_result["messages"][-1].content == "retry cevabı"

    # The model's SECOND call must never have seen "ilk cevap" — this is
    # the whole point of forking instead of appending.
    assert node.seen_message_contents[0] == ["soru"]
    assert node.seen_message_contents[1] == ["soru"], (
        "the retry's model call saw the rejected response in its context: "
        f"{node.seen_message_contents[1]}"
    )

    # And yet the original response stays permanently reachable: reconstruct
    # the WHOLE thread's history (both branches) exactly as
    # ChatController.get_chat_session does.
    full_history = await thread_controller.get_thread_state_history(thread_id)
    messages, _ = reconstruct_message_tree(
        full_history, thread_metadata={"persona_id": 0}, chat_session_id=thread_id
    )

    assert [m["message_type"] for m in messages] == ["user", "assistant", "assistant"]
    user_msg, ai1, ai2 = messages
    assert {ai1["message"], ai2["message"]} == {"ilk cevap", "retry cevabı"}
    assert ai1["parent_message"] == user_msg["message_id"]
    assert ai2["parent_message"] == user_msg["message_id"]
    assert user_msg["latest_child_message"] == ai2["message_id"]
