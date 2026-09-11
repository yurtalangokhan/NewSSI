"""A FlowAgent run parked at a HumanInput node must survive a page reload.

The live `human_input` SSE packet is gone once the stream ends, but the
interrupt itself is still in the checkpoint's pending writes. Reading it back
is what lets ChatController put the decision buttons on the reloaded turn
instead of leaving the run looking silently stuck.
"""

import pytest

from controller.thread_controller import ThreadController


class _Interrupt:
    def __init__(self, value):
        self.value = value


class _FakeTuple:
    def __init__(self, pending_writes, checkpoint_ns="", checkpoint_id="c1"):
        self.checkpoint = {"id": checkpoint_id, "channel_values": {}}
        self.pending_writes = pending_writes
        self.config = {
            "configurable": {
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }


class _FakeSaver:
    """Stands in for a checkpointer, listing one namespace per tuple.

    The reader walks every namespace of the thread rather than only the root:
    supervisor sub-agents, pipeline stages and the flow canvas' agent node are
    all subgraphs with namespaces of their own.
    """

    def __init__(self, *tuples):
        self._tuples = tuples

    def alist(self, config):
        tuples = self._tuples

        async def _gen():
            for tup in tuples:
                yield tup

        return _gen()


_REQUEST = {
    "type": "human_input",
    "node_id": "hi-1",
    "prompt": "Bu gönderi yayınlansın mı?",
    "decisions": ["yayinla", "iptal"],
}


@pytest.mark.asyncio
async def test_returns_the_pending_human_input_request(monkeypatch):
    saver = _FakeSaver(_FakeTuple([("task-1", "__interrupt__", [_Interrupt(_REQUEST)])]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_human_input("t1") == _REQUEST


@pytest.mark.asyncio
async def test_a_bare_interrupt_value_is_also_read(monkeypatch):
    """Some savers hand back the Interrupt unwrapped rather than in a list."""
    saver = _FakeSaver(_FakeTuple([("task-1", "__interrupt__", _Interrupt(_REQUEST))]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_human_input("t1") == _REQUEST


@pytest.mark.asyncio
async def test_an_interrupt_that_is_not_a_human_input_is_ignored(monkeypatch):
    """Other agents interrupt with a plain string prompt — not our packet."""
    saver = _FakeSaver(_FakeTuple([("task-1", "__interrupt__", [_Interrupt("Doğum tarihin?")])]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_human_input("t1") is None


@pytest.mark.asyncio
async def test_no_pending_writes_means_no_request(monkeypatch):
    saver = _FakeSaver(_FakeTuple([]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_human_input("t1") is None


@pytest.mark.asyncio
async def test_no_checkpointer_is_not_an_error(monkeypatch):
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: None)

    assert await ThreadController().get_pending_human_input("t1") is None


_APPROVAL = {
    "action_requests": [
        {
            "name": "send_email",
            "args": {"to": "a@b.com"},
            "tool_call_id": "c1",
            "risk": "destructive",
            "agent_path": ["Uzman"],
        }
    ],
    "review_configs": [{"action_name": "send_email", "allowed_decisions": ["approve", "reject"]}],
}


@pytest.mark.asyncio
async def test_a_pending_tool_approval_is_reported_with_its_kind(monkeypatch):
    saver = _FakeSaver(_FakeTuple([("task-1", "__interrupt__", [_Interrupt(_APPROVAL)])]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    pending = await ThreadController().get_pending_interrupt("t1")

    assert pending is not None
    assert pending.kind == "tool_approval"
    assert pending.action_count == 1


@pytest.mark.asyncio
async def test_an_approval_is_not_mistaken_for_a_human_input(monkeypatch):
    """İki interrupt türü farklı renderer ve farklı resume şekli istiyor."""
    saver = _FakeSaver(_FakeTuple([("task-1", "__interrupt__", [_Interrupt(_APPROVAL)])]))
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_human_input("t1") is None


@pytest.mark.asyncio
async def test_an_interrupt_living_only_in_a_subgraph_namespace_is_found(monkeypatch):
    """Supervisor alt agent'ı, pipeline aşaması ve flow'un agent node'u alt graf.

    Kök namespace'in yazımları boş olsa bile alt grafınki taranmalı — aksi
    halde bu senaryolarda kart reload'da geri gelmez.
    """
    saver = _FakeSaver(
        _FakeTuple([], checkpoint_ns=""),  # kök namespace: bir şey yok
        _FakeTuple(
            [("task-9", "__interrupt__", [_Interrupt(_APPROVAL)])],
            checkpoint_ns="PipelineStage-x:uuid",
        ),  # alt graf
    )
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    pending = await ThreadController().get_pending_interrupt("t1")

    assert pending is not None and pending.kind == "tool_approval"


@pytest.mark.asyncio
async def test_a_resolved_interrupt_on_an_older_checkpoint_is_not_reported(monkeypatch):
    """A finished run keeps a dead ``__interrupt__`` write on the checkpoint it
    first parked at. ``alist`` is newest-first, so once a namespace's tip has
    been inspected every older checkpoint of it must be skipped — otherwise the
    decision card comes back on every reload of an already-answered turn."""
    saver = _FakeSaver(
        # tip: run moved on, nothing pending
        _FakeTuple([], checkpoint_ns="", checkpoint_id="c-tip"),
        # older: the HumanInput interrupt that has since been resumed
        _FakeTuple(
            [("task-1", "__interrupt__", [_Interrupt(_REQUEST)])],
            checkpoint_ns="",
            checkpoint_id="c-old",
        ),
    )
    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: saver)

    assert await ThreadController().get_pending_interrupt("t1") is None
    assert await ThreadController().get_pending_human_input("t1") is None


@pytest.mark.asyncio
async def test_an_unreadable_checkpoint_is_not_an_error(monkeypatch):
    class _Broken:
        def alist(self, config):
            raise RuntimeError("checkpointer down")

    monkeypatch.setattr("controller.thread_controller.get_checkpointer", lambda: _Broken())

    assert await ThreadController().get_pending_interrupt("t1") is None
