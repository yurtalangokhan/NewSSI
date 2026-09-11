"""The SSE stream never carries a real, persisted message id for the turn it
just produced (ids are positions computed by ChatController.get_chat_session
on read, not stored). Without resolving one at the end of the stream, the
frontend can't retry or switch to this message until the page is reloaded.
message_generator must emit a trailing {user_message_id, reserved_assistant_message_id}
packet once generation finishes, by reading back the just-persisted history."""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from models.chat import StreamInput


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


class _FakeChatControllerForIds:
    """Stand-in for ChatController — returns a canned reconstructed history
    ending in the message id resolution needs to pick up."""

    last_init_kwargs: dict | None = None

    def __init__(self, **kwargs):
        _FakeChatControllerForIds.last_init_kwargs = kwargs

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
    controller: type = _FakeChatControllerForIds,
) -> list[dict]:
    from service import AgentStreamService as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_SimpleAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)
    monkeypatch.setattr("controller.ChatController", controller)
    monkeypatch.setattr("controller.get_thread_controller", lambda: None)

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
    from service import AgentStreamService as agent_message_stream

    class _BoomChatController:
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
    monkeypatch.setattr("controller.ChatController", _BoomChatController)
    monkeypatch.setattr("controller.get_thread_controller", lambda: None)

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


class _NoAssistantTurnChatController:
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
    packets = await _run(
        monkeypatch, thread_id="thread-1", controller=_NoAssistantTurnChatController
    )

    assert not any("reserved_assistant_message_id" in p for p in packets)
