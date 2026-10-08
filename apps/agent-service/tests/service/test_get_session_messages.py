"""get_session_messages resolves the real message ids emitted at the end of a
stream (the frontend's retry button needs them). It must read what the
checkpointer's ``alist`` actually yields — ``CheckpointTuple`` objects whose
messages live under ``checkpoint["channel_values"]`` — not a ``.values``
attribute that only exists on ``StateSnapshot``."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from service.chat.chat_history_reconstruction import get_session_messages


class _CheckpointTuple:
    def __init__(self, checkpoint_id, messages, parent_checkpoint_id=None):
        self.checkpoint = {"id": checkpoint_id, "ts": None, "channel_values": {"messages": messages}}
        self.config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
        self.parent_config = (
            {"configurable": {"checkpoint_id": parent_checkpoint_id}} if parent_checkpoint_id else None
        )


class _Saver:
    def __init__(self, tuples):
        self._tuples = tuples

    async def alist(self, _config):
        for t in self._tuples:
            yield t


@pytest.mark.asyncio
async def test_resolves_ids_from_checkpoint_tuples(monkeypatch):
    saver = _Saver(
        [
            _CheckpointTuple("cp-2", [HumanMessage(content="soru", id="h1"), AIMessage(content="cevap", id="a1")], "cp-1"),
            _CheckpointTuple("cp-1", [HumanMessage(content="soru", id="h1")]),
        ]
    )
    monkeypatch.setattr("service.threads.thread_access_service.get_checkpointer", lambda: saver)

    async def _get_thread(self, thread_id):
        return {"thread_id": thread_id, "metadata": {}}

    monkeypatch.setattr(
        "service.threads.thread_access_service.ThreadAccessService.get_thread", _get_thread
    )

    messages = await get_session_messages("thread-1")

    assert [(m["message_type"], m["message_id"], m["parent_message"]) for m in messages] == [
        ("user", 1, None),
        ("assistant", 2, 1),
    ]
