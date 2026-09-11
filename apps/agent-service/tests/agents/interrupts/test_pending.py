"""`_as_pending`: bir ``__interrupt__`` yazımının yorumu.

Interrupt'ı BULAN tarama `ThreadController.get_pending_interrupt`'te ve
kendi testleri var (`tests/controller/test_thread_controller_pending_human_input.py`).
Burası yalnızca tek bir değeri tanınmış bir `PendingInterrupt`'e çeviren
saf fonksiyonu doğruluyor.
"""

from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt

from agents.interrupts.pending import PendingInterrupt, _as_pending

APPROVAL = {
    "action_requests": [
        {"name": "send_email", "args": {}, "tool_call_id": "c1"},
        {"name": "file_write", "args": {}, "tool_call_id": "c2"},
    ],
    "review_configs": [
        {"action_name": "send_email", "allowed_decisions": ["approve"]},
        {"action_name": "file_write", "allowed_decisions": ["approve"]},
    ],
}


def _itr(value, id_="i1"):
    return SimpleNamespace(value=value, id=id_)


def test_reads_a_tool_approval_and_counts_its_actions():
    pending = _as_pending(_itr(APPROVAL))
    assert isinstance(pending, PendingInterrupt)
    assert pending.kind == "tool_approval"
    assert pending.action_count == 2
    assert pending.interrupt_id == "i1"


def test_reads_a_user_clarification():
    pending = _as_pending(_itr({"type": "user_clarification", "v": 1, "questions": []}))
    assert pending.kind == "user_clarification"
    # action_count yalnızca onay kapısına özgü.
    assert pending.action_count == 0


def test_reads_a_flow_human_input():
    pending = _as_pending(_itr({"type": "human_input", "prompt": "?"}))
    assert pending.kind == "human_input"
    assert pending.action_count == 0


def test_a_bare_value_without_an_id_is_still_read():
    """Bazı saver'lar Interrupt'ı sarmadan, çıplak dict olarak veriyor."""
    pending = _as_pending({"type": "user_clarification"})
    assert pending is not None and pending.kind == "user_clarification"
    assert pending.interrupt_id == ""


def test_an_unknown_shape_is_not_ours():
    assert _as_pending(_itr("düz metin bir prompt")) is None
    assert _as_pending(_itr({"action_requests": []})) is None  # review_configs eksik


# --- E12: iki alt agent aynı anda interrupt edemez ---------------------------
# Tasarım gerekçesi yapısal: supervisor handoff temelli, pipeline sıralı —
# bir anda tek alt agent koşar, dolayısıyla tek bir bekleyen interrupt olur.
# Kırılırsa `Command(resume={interrupt_id: value})` haritasına geçilir; paket
# zaten `request_id` taşıdığı için sözleşme değişmez.


def _stage(tag):
    def _node(_state):
        interrupt({"type": "user_clarification", "v": 1, "questions": [], "stage": tag})
        return {}

    return _node


@pytest.mark.asyncio
async def test_a_sequential_pipeline_surfaces_one_interrupt_at_a_time():
    builder = StateGraph(MessagesState)
    builder.add_node("stage_a", _stage("a"))
    builder.add_node("stage_b", _stage("b"))
    builder.add_edge(START, "stage_a")
    builder.add_edge("stage_a", "stage_b")
    builder.add_edge("stage_b", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-e12"}}

    first = await graph.ainvoke({"messages": []}, config)
    assert len(first["__interrupt__"]) == 1
    assert first["__interrupt__"][0].value["stage"] == "a"

    from langgraph.types import Command

    second = await graph.ainvoke(Command(resume={"answered": True, "answers": {}}), config)
    # stage_a bitti, stage_b durdu — yine tek interrupt, ikisi birden değil.
    assert len(second["__interrupt__"]) == 1
    assert second["__interrupt__"][0].value["stage"] == "b"
