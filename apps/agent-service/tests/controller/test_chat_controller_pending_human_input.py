"""A reloaded chat session re-offers a paused run's decision buttons.

The live `human_input` packet is gone after the stream ends, so the reloaded
turn gets one replayed from the checkpoint's pending interrupt — otherwise the
run looks silently stuck and the only way forward is guessing the action label.
"""

import pytest

from agents.interrupts.pending import PendingInterrupt
from controller.chat_controller import ChatController

_REQUEST = {
    "type": "human_input",
    "node_id": "hi-1",
    "prompt": "Bu gönderi yayınlansın mı?",
    "decisions": ["yayinla", "iptal"],
}


def _pending(value, interrupt_id="i1"):
    from agents.interrupts.classify import classify_interrupt

    return PendingInterrupt(
        kind=classify_interrupt(value) or "",
        value=value,
        interrupt_id=interrupt_id,
        action_count=0,
    )


def _controller(monkeypatch, pending, packets_2d):
    ctrl = ChatController.__new__(ChatController)

    class _Threads:
        async def get_thread(self, _):
            return {"thread_id": "t1", "metadata": {"name": "S"}}

        async def mark_accessed(self, _):
            return None

        async def get_thread_state_history(self, _):
            return [{"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": []}]

        async def get_pending_interrupt(self, _):
            return pending

    ctrl._thread_controller = _Threads()

    async def _belongs(*_a, **_k):
        return True

    ctrl._ensure_thread_belongs_to_user = _belongs
    monkeypatch.setattr(
        "controller.chat_controller.reconstruct_message_tree",
        lambda *a, **k: ([{"message_id": 1, "message_type": "assistant"}], packets_2d),
    )
    return ctrl


@pytest.mark.asyncio
async def test_pending_request_is_appended_to_the_last_turn(monkeypatch):
    ctrl = _controller(
        monkeypatch,
        _pending(_REQUEST),
        [[{"placement": {"turn_index": 0}, "obj": {"type": "message_start"}}]],
    )

    result = await ctrl.get_chat_session("t1")

    last_turn = result["packets"][-1]
    assert last_turn[-1]["obj"] == _REQUEST
    # Its own turn, so the client does not merge it into the answer's group.
    assert last_turn[-1]["placement"]["turn_index"] == 1


@pytest.mark.asyncio
async def test_nothing_pending_leaves_the_packets_untouched(monkeypatch):
    original = [[{"obj": {"type": "message_start"}}]]
    ctrl = _controller(monkeypatch, None, original)

    result = await ctrl.get_chat_session("t1")

    assert result["packets"] == original


@pytest.mark.asyncio
async def test_a_pending_request_with_no_turns_yet_opens_one(monkeypatch):
    ctrl = _controller(monkeypatch, _pending(_REQUEST), [])

    result = await ctrl.get_chat_session("t1")

    assert len(result["packets"]) == 1
    assert result["packets"][0][0]["obj"] == _REQUEST


@pytest.mark.asyncio
async def test_a_pending_question_is_replayed_as_a_clarification_card(monkeypatch):
    """`ask_user` payload'ı bir paket DEĞİL — pakete çevrilmesi gerekiyor."""
    value = {
        "type": "user_clarification",
        "v": 1,
        "questions": [
            {
                "question": "Raporu kim okuyacak?",
                "header": "Hedef kitle",
                "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
            }
        ],
        "agent_path": ["Fatura Uzmanı"],
    }
    ctrl = _controller(
        monkeypatch,
        _pending(value, "int-7"),
        [[{"placement": {"turn_index": 0}, "obj": {"type": "message_start"}}]],
    )

    result = await ctrl.get_chat_session("t1")

    packet = result["packets"][-1][-1]["obj"]
    assert packet["type"] == "user_clarification"
    assert packet["request_id"] == "int-7"
    assert packet["questions"][0]["header"] == "Hedef kitle"
    assert packet["agent_path"] == ["Fatura Uzmanı"]


@pytest.mark.asyncio
async def test_a_pause_before_any_answer_gets_a_synthetic_assistant_row(monkeypatch):
    """`ask_user` as the model's first act interrupts the node before it
    returns, so nothing assistant-side is persisted. A packet group with no
    `messages` row never renders — reload must synthesise that row."""
    value = {"type": "user_clarification", "v": 1, "questions": [], "agent_path": []}
    ctrl = _controller(monkeypatch, _pending(value, "int-9"), [])
    monkeypatch.setattr(
        "controller.chat_controller.reconstruct_message_tree",
        lambda *a, **k: ([{"message_id": 1, "message_type": "user", "message": "rapor"}], []),
    )

    result = await ctrl.get_chat_session("t1")

    types = [m["message_type"] for m in result["messages"]]
    assert types == ["user", "assistant"]
    synthetic = result["messages"][-1]
    assert synthetic["parent_message"] == 1
    assert synthetic["message_id"] == 2
    assert result["messages"][0]["latest_child_message"] == 2

    packet_objs = [p["obj"] for p in result["packets"][-1]]
    packet_types = [o.get("type") for o in packet_objs]
    # The card is in a group, and now there is a bubble to hang it on.
    assert "user_clarification" in packet_types
    # ...plus a stop, so reload does not read the turn as still streaming.
    assert "stop" in packet_types
    clar_turn = next(
        p["placement"]["turn_index"]
        for p in result["packets"][-1]
        if p["obj"].get("type") == "user_clarification"
    )
    stop_turn = next(
        p["placement"]["turn_index"]
        for p in result["packets"][-1]
        if p["obj"].get("type") == "stop"
    )
    # The stop is on its own turn — it must not merge into the card's group
    # or the text renderer wins and the card never shows.
    assert stop_turn != clar_turn


@pytest.mark.asyncio
async def test_a_pause_after_a_streamed_answer_keeps_its_real_message(monkeypatch):
    """Regression: when an assistant message was already persisted, no
    synthetic row is added on top of it."""
    value = {"type": "user_clarification", "v": 1, "questions": [], "agent_path": []}
    ctrl = _controller(monkeypatch, _pending(value, "int-10"), [])
    monkeypatch.setattr(
        "controller.chat_controller.reconstruct_message_tree",
        lambda *a, **k: (
            [
                {"message_id": 1, "message_type": "user"},
                {"message_id": 2, "message_type": "assistant", "message": "kısmi cevap"},
            ],
            [],
        ),
    )

    result = await ctrl.get_chat_session("t1")

    assert [m["message_type"] for m in result["messages"]] == ["user", "assistant"]
    assert result["messages"][-1]["message"] == "kısmi cevap"


@pytest.mark.asyncio
async def test_an_unreadable_checkpoint_loses_the_buttons_not_the_conversation(monkeypatch):
    ctrl = _controller(monkeypatch, None, [])

    async def _boom(_):
        raise RuntimeError("checkpointer down")

    ctrl._thread_controller.get_pending_interrupt = _boom

    result = await ctrl.get_chat_session("t1")
    assert result["packets"] == []
