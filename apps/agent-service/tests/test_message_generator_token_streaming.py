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


class _RepeatedSameNameToolCallAgent:
    """A deep-research loop calling the same-named tool more than once."""

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
                        AIMessage(
                            id="tool-call-1",
                            content="",
                            tool_calls=[
                                {"name": "web_search", "args": {"query": "a"}, "id": "call-1"}
                            ],
                        ),
                        ToolMessage(content="result a", tool_call_id="call-1", name="web_search"),
                        AIMessage(
                            id="tool-call-2",
                            content="",
                            tool_calls=[
                                {"name": "web_search", "args": {"query": "b"}, "id": "call-2"}
                            ],
                        ),
                        ToolMessage(content="result b", tool_call_id="call-2", name="web_search"),
                        AIMessage(id=ANSWER_MESSAGE_ID, content="Hazır."),
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
    # Nothing visible was written before the tool call, so the answer starts
    # clean — no separator should be injected ahead of it.
    assert "".join(tokens) == "Raporunuz hazır."


@pytest.mark.asyncio
async def test_repeated_calls_to_the_same_named_tool_each_get_a_start_packet(monkeypatch):
    """A deep-research loop calling e.g. web_search several times must surface
    every call's custom_tool_start, not just the first — deduping by tool name
    instead of call id silently drops the timeline entry for every repeat call
    while its result still streams through."""
    packets = await _run(monkeypatch, _RepeatedSameNameToolCallAgent())

    starts = [p for p in packets if p["type"] == "custom_tool_start"]
    assert len(starts) == 2
    assert [s["args"] for s in starts] == [{"query": "a"}, {"query": "b"}]


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


class _NativeReasoningPlusContentAgent:
    """A chunk that carries both visible content and a native reasoning
    field (e.g. Ollama's reasoning_content) at the same time."""

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
                    id="answer-call",
                    content="Hello",
                    additional_kwargs={"reasoning_content": "thinking about it"},
                ),
                {},
            ),
        )


@pytest.mark.asyncio
async def test_reasoning_is_not_dropped_when_content_is_also_present(monkeypatch):
    """A tag-based-model chunk carrying both a native `reasoning_content`
    field and visible `content` at once must surface both — dropping the
    reasoning whenever content is also present makes the model look like it
    abruptly left its thinking phase without ever showing that reasoning."""
    packets = await _run(monkeypatch, _NativeReasoningPlusContentAgent())

    types = [p["type"] for p in packets]
    assert "reasoning_delta" in types
    assert "token" in types
    # Reasoning for a chunk is surfaced before that chunk's visible text.
    assert types.index("reasoning_delta") < types.index("token")


class _SlowDocumentToolAgent:
    """A provider that goes silent while the model writes a document.

    Ollama (via langchain-ollama) hands over only the *completed* tool call,
    so nothing at all reaches the stream while the body is being written —
    `DocumentProgressTracker` has no argument chunks to report progress from.
    """

    def __init__(self, *, quiet_seconds: float) -> None:
        self._quiet_seconds = quiet_seconds

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        import asyncio as _asyncio

        # The model is writing the document body — no chunks reach us.
        await _asyncio.sleep(self._quiet_seconds)
        yield _answer_chunk("Hazır.")


@pytest.mark.asyncio
async def test_long_silent_generation_still_emits_keep_alive(monkeypatch):
    """A silent stretch must not leave the SSE connection idle.

    Proxies in front of the stream (Kong defaults to a 60s read timeout) tear
    down connections that go quiet, which reaches the browser as
    ERR_INCOMPLETE_CHUNKED_ENCODING mid-answer.
    """
    from api.routes import AgentsRoute

    monkeypatch.setattr(AgentsRoute.settings, "STREAM_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_SlowDocumentToolAgent(quiet_seconds=0.3)),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    chunks = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="rapor hazırla"),
        agent_id="chatbot",
        user_id="user-1",
    ):
        chunks.append(chunk)

    keep_alives = [c for c in chunks if c.startswith(":")]
    assert keep_alives, "a silent generation sent nothing to hold the connection open"
    # Keep-alives are SSE comments, so they must not look like packets.
    assert all("data:" not in c for c in keep_alives)
    # The real answer still comes through afterwards.
    assert any('"token"' in c for c in chunks)


class _InterruptedSentenceAgent:
    """A model that breaks off mid-answer to call a tool, then resumes.

    `tail` is the last thing written before the tool call and `resume` the
    first thing written after it, so a test can pick whether the two halves
    would run together.
    """

    def __init__(self, *, tail: str, resume: str) -> None:
        self._tail = tail
        self._resume = resume

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield _answer_chunk(self._tail, message_id="call-1")
        # The node returns, reporting the tool call it made.
        yield (
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            id="tool-call",
                            content="",
                            tool_calls=[
                                {"name": "web_search", "args": {"q": "x"}, "id": "c1"}
                            ],
                        ),
                        ToolMessage(content="ok", tool_call_id="c1", name="web_search"),
                    ]
                }
            },
        )
        yield _answer_chunk(self._resume, message_id="call-2")


async def _tokens_across_tool_call(monkeypatch, *, tail: str, resume: str) -> str:
    from api.routes import AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_InterruptedSentenceAgent(tail=tail, resume=resume)),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    packets = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="arastir"), agent_id="chatbot", user_id="user-1"
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            packets.append(json.loads(body))
    return "".join(p["content"] for p in packets if p["type"] == "token")


@pytest.mark.asyncio
async def test_answer_resumed_after_tool_call_is_not_glued_mid_word(monkeypatch):
    """A call that stopped mid-word must not run into the next one's first word."""
    answer = await _tokens_across_tool_call(
        monkeypatch, tail="Aramaları", resume="Harika, buldum."
    )

    assert "AramalarıHarika" not in answer
    assert answer == "Aramaları\n\nHarika, buldum."


@pytest.mark.asyncio
async def test_answer_resumed_mid_sentence_is_left_intact(monkeypatch):
    """A sentence continuing across the tool call must not be split.

    The model often breaks off after a space and finishes the thought
    afterwards; forcing a paragraph break there would cut the sentence in
    half instead of healing anything.
    """
    answer = await _tokens_across_tool_call(
        monkeypatch, tail="kritik sayfaları ", resume="okuyalım."
    )

    assert answer == "kritik sayfaları okuyalım."

class _TrailingWordBeforeToolAgent:
    """A call whose last word has no trailing space, then its tool call.

    The tag processor buffers up to the final whitespace, so that word is
    still held when the tool call is announced.
    """

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield _answer_chunk("sayfalari fetch_webpage ile ", message_id="call-1")
        # No trailing space: the processor holds this back.
        yield _answer_chunk("okuyacagim:", message_id="call-1")
        # Same chunk stream announces the tool call.
        yield (
            "messages",
            (
                AIMessageChunk(
                    id="call-1",
                    content="",
                    tool_call_chunks=[
                        {"name": "fetch_webpage", "args": "{}", "id": "c1", "index": 0}
                    ],
                ),
                {},
            ),
        )


@pytest.mark.asyncio
async def test_trailing_word_is_flushed_before_its_tool_steps(monkeypatch):
    """The word must not land below the tool cards it introduces.

    Arriving after `custom_tool_start` puts it in a display group of its own
    underneath the tool steps, so the sentence renders split across lines.
    """
    packets = await _run(monkeypatch, _TrailingWordBeforeToolAgent())
    types = [p["type"] for p in packets]

    assert "okuyacagim:" in "".join(
        p["content"] for p in packets if p["type"] == "token"
    )
    last_token = len(types) - 1 - types[::-1].index("token")
    first_tool = types.index("custom_tool_start")
    assert last_token < first_tool, (
        "answer text arrived after the tool steps it introduces"
    )

class _QuietWhileWritingDocumentAgent:
    """Writes a sentence, then goes quiet while composing a document.

    Ollama withholds tool-call arguments until the call is complete, so the
    document phase reaches the stream as pure silence.
    """

    def __init__(self, *, quiet_seconds: float) -> None:
        self._quiet_seconds = quiet_seconds

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        import asyncio as _asyncio

        yield _answer_chunk("sayfalara erisme ", message_id="call-1")
        # No trailing space, so the tag processor holds this word back.
        yield _answer_chunk("gerekiyor:", message_id="call-1")
        await _asyncio.sleep(self._quiet_seconds)
        yield _tool_args_chunk(
            '{"filename": "r", "format": "pdf", "content": "x"}', name="create_document"
        )


@pytest.mark.asyncio
async def test_buffered_word_is_released_while_the_stream_is_quiet(monkeypatch):
    """The tail of a sentence must not wait out the whole document phase.

    Held in the buffer it renders nowhere, leaving a frozen cursor for as
    long as the document takes and appearing only once it is finished.
    """
    from api.routes import AgentsRoute

    monkeypatch.setattr(AgentsRoute.settings, "STREAM_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_QuietWhileWritingDocumentAgent(quiet_seconds=0.3)),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    seen_word_at = None
    seen_document_at = None
    for index, chunk in enumerate(
        [c async for c in AgentsRoute.message_generator(
            StreamInput(message="arastir"), agent_id="chatbot", user_id="user-1"
        )]
    ):
        if seen_word_at is None and "gerekiyor:" in chunk:
            seen_word_at = index
        if seen_document_at is None and "document_generation_start" in chunk:
            seen_document_at = index

    assert seen_word_at is not None, "the buffered word never reached the client"
    assert seen_document_at is not None
    assert seen_word_at < seen_document_at, (
        "the word only appeared once the document was done"
    )
