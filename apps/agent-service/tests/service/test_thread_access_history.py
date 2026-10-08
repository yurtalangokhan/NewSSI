"""ThreadAccessService.get_thread_state_history exposes every checkpoint of a
thread — across every branch, not just the current tip's ancestry — so
ChatManagementService.get_chat_session can reconstruct a retried-away-from
response instead of losing it once it's no longer the latest checkpoint.
"""

from error_contract import InternalServerError
import pytest

from service.threads.thread_access_service import ThreadAccessService


class _FakeCheckpointTuple:
    def __init__(self, checkpoint_id, messages, parent_checkpoint_id=None, checkpoint_ns=""):
        self.checkpoint = {"id": checkpoint_id, "channel_values": {"messages": messages}}
        self.config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": checkpoint_ns}}
        self.parent_config = (
            {"configurable": {"checkpoint_id": parent_checkpoint_id}}
            if parent_checkpoint_id is not None
            else None
        )


class _FakeSaver:
    def __init__(self, tuples):
        self._tuples = tuples
        self.last_config = None

    async def alist(self, config):
        self.last_config = config
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
    monkeypatch.setattr(
        "service.threads.thread_access_service.get_checkpointer", lambda: fake_saver
    )

    service = ThreadAccessService()
    history = await service.get_thread_state_history("thread-1")

    assert {c["checkpoint_id"] for c in history} == {"root", "branch-a", "branch-b"}
    by_id = {c["checkpoint_id"]: c for c in history}
    assert by_id["root"]["parent_checkpoint_id"] is None
    assert by_id["branch-a"]["parent_checkpoint_id"] == "root"
    assert by_id["branch-b"]["parent_checkpoint_id"] == "root"
    assert [m["content"] for m in by_id["branch-a"]["messages"]] == ["soru", "cevap 1"]


@pytest.mark.asyncio
async def test_get_thread_state_history_excludes_subgraph_namespace_checkpoints(
    monkeypatch,
):
    """A FlowAgent turn also writes checkpoints under a subgraph namespace
    (an embedded agent-execution node). Those must never reach
    reconstruct_message_tree — they are not branches of the conversation."""
    from langchain_core.messages import AIMessage, HumanMessage

    fake_saver = _FakeSaver(
        [
            _FakeCheckpointTuple("root", [HumanMessage(content="soru")]),
            _FakeCheckpointTuple(
                "tip",
                [HumanMessage(content="soru"), AIMessage(content="cevap")],
                parent_checkpoint_id="root",
            ),
            _FakeCheckpointTuple(
                "subgraph-cp",
                [HumanMessage(content="alt görev"), AIMessage(content="alt cevap")],
                checkpoint_ns="ReActAgent-abc123:0",
            ),
        ]
    )
    monkeypatch.setattr(
        "service.threads.thread_access_service.get_checkpointer", lambda: fake_saver
    )

    service = ThreadAccessService()
    history = await service.get_thread_state_history("thread-1")

    assert fake_saver.last_config["configurable"]["checkpoint_ns"] == ""
    assert {c["checkpoint_id"] for c in history} == {"root", "tip"}


@pytest.mark.asyncio
async def test_get_thread_state_history_returns_empty_list_without_a_checkpointer(
    monkeypatch,
):
    monkeypatch.setattr("service.threads.thread_access_service.get_checkpointer", lambda: None)

    service = ThreadAccessService()
    history = await service.get_thread_state_history("thread-1")

    assert history == []


@pytest.mark.asyncio
async def test_get_thread_state_history_reports_checkpointer_failure_as_a_typed_error(
    monkeypatch,
):
    class _BoomSaver:
        async def alist(self, config):
            raise RuntimeError("boom")
            yield  # pragma: no cover - never reached, makes this an async generator

    monkeypatch.setattr(
        "service.threads.thread_access_service.get_checkpointer", lambda: _BoomSaver()
    )

    service = ThreadAccessService()
    with pytest.raises(InternalServerError):
        await service.get_thread_state_history("thread-1")


@pytest.mark.asyncio
async def test_get_thread_state_history_exposes_checkpoint_timestamp(monkeypatch):
    """Each checkpoint's own write time is the only record of when a turn
    happened — nothing else in the thread carries a per-message timestamp.
    Reconstruction stamps messages from it, so it has to survive this hop."""
    from langchain_core.messages import AIMessage, HumanMessage

    root = _FakeCheckpointTuple("root", [HumanMessage(content="soru")])
    root.checkpoint["ts"] = "2026-08-12T13:06:00.123456+00:00"
    child = _FakeCheckpointTuple(
        "child",
        [HumanMessage(content="soru"), AIMessage(content="cevap")],
        parent_checkpoint_id="root",
    )
    child.checkpoint["ts"] = "2026-08-12T13:06:04.654321+00:00"

    monkeypatch.setattr(
        "service.threads.thread_access_service.get_checkpointer", lambda: _FakeSaver([root, child])
    )

    history = await ThreadAccessService().get_thread_state_history("thread-1")

    by_id = {c["checkpoint_id"]: c for c in history}
    assert by_id["root"]["ts"] == "2026-08-12T13:06:00.123456+00:00"
    assert by_id["child"]["ts"] == "2026-08-12T13:06:04.654321+00:00"


@pytest.mark.asyncio
async def test_get_thread_state_history_tolerates_a_checkpoint_without_a_timestamp(
    monkeypatch,
):
    """A checkpointer stand-in may omit `ts`; that must degrade to an unstamped
    turn rather than dropping the checkpoint or raising."""
    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(
        "service.threads.thread_access_service.get_checkpointer",
        lambda: _FakeSaver([_FakeCheckpointTuple("root", [HumanMessage(content="soru")])]),
    )

    history = await ThreadAccessService().get_thread_state_history("thread-1")

    assert history[0]["ts"] is None
