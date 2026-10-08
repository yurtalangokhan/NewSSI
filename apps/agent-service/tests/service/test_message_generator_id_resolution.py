"""The SSE stream never carries a real, persisted message id for the turn it
just produced (ids are positions computed by ChatManagementService.get_chat_session
on read, not stored). Without resolving one at the end of the stream, the
frontend can't retry or switch to this message until the page is reloaded.
message_generator must emit a trailing {user_message_id, reserved_assistant_message_id}
packet once generation finishes, by reading back the just-persisted history."""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from schemas.chat import StreamInput


def _packets(chunks: list[str]) -> list[dict]:
    parsed = []
    for chunk in chunks:
        body = chunk.removeprefix("data: ").strip()
        if not body or body == "[DONE]":
            continue
        parsed.append(json.loads(body))
    return parsed


class _SimpleAgent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "updates",
            {"model": {"messages": [AIMessage(content="merhaba")]}},
        )


class _FakeAssistantService:
    def __init__(self, agent) -> None:
        self._agent = agent

    async def get_graph_and_config(self, _agent_id):
        return "chatbot", {}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return self._agent


async def _fake_handle_input(_user_input, _agent, _user_id=None):
    return {"input": {"messages": []}, "config": {}}, uuid4()


class _FakeChatServiceForIds:
    """Stand-in for ChatManagementService — returns a canned reconstructed history
    ending in the message id resolution needs to pick up."""

    last_init_kwargs: dict | None = None

    def __init__(self, **kwargs):
        _FakeChatServiceForIds.last_init_kwargs = kwargs

    async def get_chat_session(self, thread_id: str):
        return {
            "messages": [
                {"message_id": 4, "parent_message": None, "message_type": "user"},
                {"message_id": 5, "parent_message": 4, "message_type": "assistant"},
            ]
        }


async def _run(
    monkeypatch,
    thread_id: str | None,
    message: str = "hello",
    service: type = _FakeChatServiceForIds,
) -> list[dict]:
    from service.orchestration import agent_stream_service as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_SimpleAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    async def _fake_get_session_messages(thread_id: str, **_kw) -> list[dict]:
        inst = service()
        res = await inst.get_chat_session(thread_id)
        return res.get("messages") or []

    monkeypatch.setattr(
        "service.chat.chat_history_reconstruction.get_session_messages",
        _fake_get_session_messages,
    )

    return _packets(
        [
            chunk
            async for chunk in agent_message_stream.message_generator(
                StreamInput(message=message, thread_id=thread_id),
                agent_id="chatbot",
                user_id="user-1",
            )
        ]
    )


@pytest.mark.asyncio
async def test_emits_real_message_ids_after_a_successful_turn(monkeypatch):
    packets = await _run(monkeypatch, thread_id="thread-1")

    id_packet = next((p for p in packets if "reserved_assistant_message_id" in p), None)
    assert id_packet is not None, f"no id packet in: {packets}"
    assert id_packet == {"user_message_id": 4, "reserved_assistant_message_id": 5}


@pytest.mark.asyncio
async def test_skips_id_resolution_without_a_thread_id(monkeypatch):
    """Auto-invoke / tool-runner style calls may have no thread_id at all —
    there is nothing to look up, so this must not error or emit a packet."""
    packets = await _run(monkeypatch, thread_id=None)

    assert not any("reserved_assistant_message_id" in p for p in packets)


@pytest.mark.asyncio
async def test_id_resolution_failure_does_not_break_the_stream(monkeypatch):
    from service.orchestration import agent_stream_service as agent_message_stream

    class _BoomChatService:
        def __init__(self, **kwargs):
            pass

        async def get_chat_session(self, thread_id: str):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_SimpleAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    async def _boom_get_session_messages(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "service.chat.chat_history_reconstruction.get_session_messages",
        _boom_get_session_messages,
    )

    chunks = [
        chunk
        async for chunk in agent_message_stream.message_generator(
            StreamInput(message="hello", thread_id="thread-1"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]

    # The answer itself and the terminal [DONE] must still make it through —
    # a failure resolving ids is a missed nicety, not a stream failure.
    assert any('"type": "message"' in c or '"type": "token"' in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


class _NoAssistantTurnChatService:
    """Reconstruction can end on the human message when a turn produced no
    visible assistant content (e.g. an error cut generation short before
    any assistant message was appended)."""

    def __init__(self, **kwargs):
        pass

    async def get_chat_session(self, thread_id: str):
        return {
            "messages": [
                {"message_id": 4, "parent_message": None, "message_type": "user"},
            ]
        }


@pytest.mark.asyncio
async def test_skips_id_resolution_when_the_turn_produced_no_assistant_message(
    monkeypatch,
):
    packets = await _run(monkeypatch, thread_id="thread-1", service=_NoAssistantTurnChatService)

    assert not any("reserved_assistant_message_id" in p for p in packets)
