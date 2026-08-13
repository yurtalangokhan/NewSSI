"""Token streaming across an in-node tool loop.

The default chatbot graph runs its whole document tool loop inside a single
`call_model` node, so LangGraph reports the tool-call message, the tool result
and the answer in one `updates` event *after* the node returns. Only the
`messages` stream arrives live — if the answer's chunks are filtered out there,
the reply reaches the client as one full `message` packet and renders instantly
with no streaming animation.
"""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from models.chat import StreamInput

_FILE_PAYLOAD = json.dumps(
    {
        "__generated_file__": True,
        "file_id": "abc123",
        "filename": "rapor.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 42,
        "download_url": "/api/chat/file/abc123?download=1",
    }
)

ANSWER_MESSAGE_ID = "answer-call"


def _tool_args_chunk(args: str, *, name: str | None = None) -> tuple:
    return (
        "messages",
        (
            AIMessageChunk(
                id="tool-call",
                content="",
                tool_call_chunks=[{"name": name, "args": args, "id": "call-1", "index": 0}],
            ),
            {},
        ),
    )


def _answer_chunk(text: str, message_id: str = ANSWER_MESSAGE_ID) -> tuple:
    return ("messages", (AIMessageChunk(id=message_id, content=text), {}))


class _SingleNodeToolLoopAgent:
    """Mimics chatbot.call_model: two LLM calls, one updates event at the end."""

    def __init__(self, *, extra_events: list | None = None) -> None:
        self._extra_events = extra_events or []

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        # LLM call #1 — writes the document into tool-call arguments.
        yield _tool_args_chunk(
            '{"filename": "rapor", "format": "pdf", "content": "', name="create_document"
        )
        yield _tool_args_chunk("x" * 400)

        for event in self._extra_events:
            yield event

        # LLM call #2 — the closing answer, still inside the same node.
        yield _answer_chunk("Raporunuz ")
        yield _answer_chunk("hazır.")

        # Background call (memory extraction) is tagged out of the stream.
        yield (
            "messages",
            (AIMessageChunk(id="memory-call", content="ignored"), {"tags": ["skip_stream"]}),
        )

        # The node returns: every message it produced arrives at once.
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            id="tool-call",
                            content="",
                            tool_calls=[
                                {
                                    "name": "create_document",
                                    "args": {"filename": "rapor.pdf", "format": "pdf"},
                                    "id": "call-1",
                                }
                            ],
                        ),
                        ToolMessage(
                            content=_FILE_PAYLOAD,
                            tool_call_id="call-1",
                            name="create_document",
                        ),
                        AIMessage(id=ANSWER_MESSAGE_ID, content="Raporunuz hazır."),
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


async def _run(monkeypatch, agent) -> list[dict]:
    from api.routes import AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    packets = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="rapor hazırla"),
        agent_id="chatbot",
        user_id="user-1",
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]":
            packets.append(json.loads(body))
    return packets


@pytest.mark.asyncio
async def test_answer_after_an_in_node_tool_call_streams_as_tokens(monkeypatch):
    packets = await _run(monkeypatch, _SingleNodeToolLoopAgent())

    tokens = [p["content"] for p in packets if p["type"] == "token"]
    # More than one packet is the point: the client animates what it receives,
    # so a single packet carrying the whole answer is what "no animation" means.
    assert len(tokens) > 1
    assert "".join(tokens) == "Raporunuz hazır."


@pytest.mark.asyncio
async def test_streamed_answer_is_not_repeated_as_a_full_message_packet(monkeypatch):
    packets = await _run(monkeypatch, _SingleNodeToolLoopAgent())

    assert not any(p["type"] == "message" for p in packets), (
        "the answer already streamed as tokens; a full message packet would render it a second time"
    )


@pytest.mark.asyncio
async def test_background_llm_calls_stay_out_of_the_stream(monkeypatch):
    packets = await _run(monkeypatch, _SingleNodeToolLoopAgent())

    assert not any("ignored" in json.dumps(p) for p in packets)


@pytest.mark.asyncio
async def test_document_packets_frame_the_streamed_answer(monkeypatch):
    packets = await _run(monkeypatch, _SingleNodeToolLoopAgent())
    types = [p["type"] for p in packets]

    # The skeleton opens before the answer starts and closes before the stream
    # ends, and the file is announced exactly once.
    assert types.index("document_generation_start") < types.index("token")
    assert types.count("generated_file") == 1
    assert types.count("document_generation_end") == 1


@pytest.mark.asyncio
async def test_a_tools_own_live_packets_replace_the_end_of_node_ones(monkeypatch):
    """The tool publishes the file the moment it exists, before the answer."""
    live_events = [
        (
            "custom",
            {
                "type": "document_generation_progress",
                "tool_name": "create_document",
                "filename": "rapor.pdf",
                "format": "pdf",
                "phase": "rendering",
                "chars": 400,
            },
        ),
        (
            "custom",
            {
                "type": "generated_file",
                "file_id": "abc123",
                "filename": "rapor.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 42,
                "download_url": "/api/chat/file/abc123?download=1",
            },
        ),
        (
            "custom",
            {
                "type": "document_generation_end",
                "tool_name": "create_document",
                "filename": "rapor.pdf",
                "format": "pdf",
                "status": "success",
                "error": None,
            },
        ),
    ]
    packets = await _run(monkeypatch, _SingleNodeToolLoopAgent(extra_events=live_events))
    types = [p["type"] for p in packets]

    # Announced once despite arriving both live and in the ToolMessage...
    assert types.count("generated_file") == 1
    assert types.count("document_generation_end") == 1
    # ...and early enough that the file card precedes the closing answer.
    assert types.index("generated_file") < types.index("token")
