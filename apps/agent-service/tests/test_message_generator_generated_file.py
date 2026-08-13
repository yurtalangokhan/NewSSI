"""message_generator must surface a document tool's ToolMessage as a
generated_file SSE packet, in addition to the existing tool timeline packets."""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage

from models.chat import StreamInput


class _DocumentToolAgent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        payload = json.dumps(
            {
                "__generated_file__": True,
                "file_id": "abc123",
                "filename": "rapor.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 42,
                "download_url": "/api/chat/file/abc123?download=1",
            }
        )
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        ToolMessage(
                            content=payload,
                            tool_call_id="call-1",
                            name="create_document",
                        )
                    ]
                }
            },
        )


class _PlainToolAgent:
    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        ToolMessage(
                            content="42",
                            tool_call_id="call-1",
                            name="Calculator",
                        )
                    ]
                }
            },
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


@pytest.mark.asyncio
async def test_emits_generated_file_packet_for_document_tool_result(monkeypatch):
    from api.routes import AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_DocumentToolAgent()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="rapor hazırla"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]

    generated_file_chunk = next((c for c in chunks if '"type": "generated_file"' in c), None)
    assert generated_file_chunk is not None, f"no generated_file packet in: {chunks}"
    payload = json.loads(generated_file_chunk.removeprefix("data: ").strip())

    assert payload == {
        "type": "generated_file",
        "file_id": "abc123",
        "filename": "rapor.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 42,
        "download_url": "/api/chat/file/abc123?download=1",
    }

    # The existing tool-result timeline packet must still be emitted.
    assert any('"type": "custom_tool_delta"' in c and "create_document" in c for c in chunks)


@pytest.mark.asyncio
async def test_does_not_emit_generated_file_packet_for_plain_tool_result(monkeypatch):
    from api.routes import AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_PlainToolAgent()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="2+2 kaç eder"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]

    assert not any('"type": "generated_file"' in c for c in chunks)
