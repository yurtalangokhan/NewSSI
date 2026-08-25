"""ThreadController.get_thread_state_history exposes every checkpoint of a
thread — across every branch, not just the current tip's ancestry — so
ChatController.get_chat_session can reconstruct a retried-away-from
response instead of losing it once it's no longer the latest checkpoint.
"""

import pytest

from controller.thread_controller import ThreadController


class _FakeCheckpointTuple:
    def __init__(self, checkpoint_id, messages, parent_checkpoint_id=None):
        self.checkpoint = {"id": checkpoint_id, "channel_values": {"messages": messages}}
        self.parent_config = (
            {"configurable": {"checkpoint_id": parent_checkpoint_id}}
            if parent_checkpoint_id is not None
            else None
        )


class _FakeSaver:
    def __init__(self, tuples):
        self._tuples = tuples

    async def alist(self, config):
        for t in self._tuples:
            yield t


@pytest.mark.asyncio
async def test_get_thread_state_history_returns_every_checkpoint_with_parent_links(
    monkeypatch,
):
    from langchain_core.messages import AIMessage, HumanMessage

    fake_saver = _FakeSaver(
        [
            _FakeCheckpointTuple("root", [HumanMessage(content="soru")]),
            _FakeCheckpointTuple(
                "branch-a",
                [HumanMessage(content="soru"), AIMessage(content="cevap 1")],
                parent_checkpoint_id="root",
            ),
            _FakeCheckpointTuple(
                "branch-b",
                [HumanMessage(content="soru"), AIMessage(content="cevap 2")],
                parent_checkpoint_id="root",
            ),
        ]
    )
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: fake_saver)

    controller = ThreadController()
    history = await controller.get_thread_state_history("thread-1")

    assert {c["checkpoint_id"] for c in history} == {"root", "branch-a", "branch-b"}
    by_id = {c["checkpoint_id"]: c for c in history}
    assert by_id["root"]["parent_checkpoint_id"] is None
    assert by_id["branch-a"]["parent_checkpoint_id"] == "root"
    assert by_id["branch-b"]["parent_checkpoint_id"] == "root"
    assert [m["content"] for m in by_id["branch-a"]["messages"]] == ["soru", "cevap 1"]


@pytest.mark.asyncio
async def test_get_thread_state_history_returns_empty_list_without_a_checkpointer(
    monkeypatch,
):
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: None)

    controller = ThreadController()
    history = await controller.get_thread_state_history("thread-1")

    assert history == []


@pytest.mark.asyncio
async def test_get_thread_state_history_returns_empty_list_on_checkpointer_failure(
    monkeypatch,
):
    class _BoomSaver:
        async def alist(self, config):
            raise RuntimeError("boom")
            yield  # pragma: no cover - never reached, makes this an async generator

    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: _BoomSaver())

    controller = ThreadController()
    history = await controller.get_thread_state_history("thread-1")

    assert history == []
