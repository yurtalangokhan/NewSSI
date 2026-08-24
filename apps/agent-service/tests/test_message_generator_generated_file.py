"""message_generator must surface a document tool's ToolMessage as a
generated_file SSE packet, and frame the (slow) generation with
document_generation_* progress packets instead of a generic tool step."""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from models.chat import StreamInput

_GENERATED_FILE_PAYLOAD = json.dumps(
    {
        "__generated_file__": True,
        "file_id": "abc123",
        "filename": "rapor.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 42,
        "download_url": "/api/chat/file/abc123?download=1",
    }
)


def _packets(chunks: list[str]) -> list[dict]:
    parsed = []
    for chunk in chunks:
        body = chunk.removeprefix("data: ").strip()
        if not body or body == "[DONE]":
            continue
        parsed.append(json.loads(body))
    return parsed


class _DocumentToolAgent:
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
                            content=_GENERATED_FILE_PAYLOAD,
                            tool_call_id="call-1",
                            name="create_document",
                        )
                    ]
                }
            },
        )


class _StreamingDocumentToolAgent:
    """Mimics a model writing a document into streamed tool-call arguments."""

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": "create_document",
                            "args": '{"filename": "rapor", "format": "pdf", "content": "',
                            "id": "call-1",
                            "index": 0,
                        }
                    ],
                ),
                {},
            ),
        )
        for _ in range(3):
            yield (
                "messages",
                (
                    AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {"name": None, "args": "x" * 400, "id": None, "index": 0}
                        ],
                    ),
                    {},
                ),
            )
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "create_document",
                                    "args": {
                                        "filename": "rapor.pdf",
                                        "format": "pdf",
                                        "content": "x" * 1200,
                                    },
                                    "id": "call-1",
                                }
                            ],
                        )
                    ]
                }
            },
        )
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        ToolMessage(
                            content=_GENERATED_FILE_PAYLOAD,
                            tool_call_id="call-1",
                            name="create_document",
                        )
                    ]
                }
            },
        )


class _StalledDocumentToolAgent:
    """A generation that never produces a tool result (stream dies mid-write)."""

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": "create_document",
                            "args": '{"filename": "rapor",',
                            "id": "call-1",
                            "index": 0,
                        }
                    ],
                ),
                {},
            ),
        )
        raise RuntimeError("upstream provider dropped the connection")


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

    # The file card replaces the generic tool step for document tools, so no
    # raw tool payload is echoed into the timeline.
    assert not any('"type": "custom_tool_delta"' in c for c in chunks)


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
    assert not any("document_generation" in c for c in chunks)


async def _run(monkeypatch, agent, message: str = "rapor hazırla") -> list[dict]:
    from api.routes import AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    return _packets(
        [
            chunk
            async for chunk in AgentsRoute.message_generator(
                StreamInput(message=message),
                agent_id="chatbot",
                user_id="user-1",
            )
        ]
    )


@pytest.mark.asyncio
async def test_streamed_document_arguments_produce_progress_packets(monkeypatch):
    """The document body streams as tool-call args and emits no tokens — without
    these packets the frontend would show nothing at all while it is written."""
    packets = await _run(monkeypatch, _StreamingDocumentToolAgent())

    types = [packet["type"] for packet in packets]
    assert types.index("document_generation_start") < types.index("generated_file")
    assert "document_generation_progress" in types
    assert types[-1] == "document_generation_end"

    start = packets[types.index("document_generation_start")]
    assert start["tool_name"] == "create_document"
    assert start["phase"] == "writing"

    progress = [p for p in packets if p["type"] == "document_generation_progress"]
    assert [p["chars"] for p in progress] == sorted(p["chars"] for p in progress)
    # Metadata is recovered from the partially streamed JSON arguments.
    assert progress[0]["filename"] == "rapor"
    assert progress[0]["format"] == "pdf"
    # The last progress packet marks the switch from writing to rendering bytes.
    assert progress[-1]["phase"] == "rendering"

    end = packets[-1]
    assert end["status"] == "success"
    assert end["filename"] == "rapor.pdf"


@pytest.mark.asyncio
async def test_document_generation_is_closed_when_the_stream_fails(monkeypatch):
    packets = await _run(monkeypatch, _StalledDocumentToolAgent())

    types = [packet["type"] for packet in packets]
    assert "document_generation_start" in types
    assert types[-1] == "document_generation_end"
    assert packets[-1]["status"] == "incomplete"


@pytest.mark.asyncio
async def test_document_tool_call_does_not_emit_a_generic_tool_step(monkeypatch):
    """A document tool call must be represented only by document_generation_*
    packets. A generic custom_tool_start for the same call would fall outside
    the frontend's document-generation exemption and reset its in-progress
    answer streaming state, breaking mid-answer document generation."""
    packets = await _run(monkeypatch, _StreamingDocumentToolAgent())

    assert not any(
        p["type"] in ("custom_tool_start", "custom_tool_delta")
        and p.get("tool_name") == "create_document"
        for p in packets
    )
    assert any(p["type"] == "document_generation_start" for p in packets)
