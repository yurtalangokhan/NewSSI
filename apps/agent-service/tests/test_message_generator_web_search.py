"""message_generator must translate web_search/fetch_webpage tool calls
into search_tool_*/open_url_* packets instead of the generic
custom_tool_start/custom_tool_delta every other tool gets."""

import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from models.chat import StreamInput

_WEB_SEARCH_RESULT = (
    "TITLE: Onyx: Open Source AI Platform\n"
    "URL: https://onyx.app\n"
    "SNIPPET: Onyx is the open source generative AI platform."
)

_FETCH_RESULT = "TITLE: Onyx\nDESCRIPTION: Open source AI platform.\n---\nFull body."


def _packets(chunks: list[str]) -> list[dict]:
    parsed = []
    for chunk in chunks:
        body = chunk.removeprefix("data: ").strip()
        if not body or body == "[DONE]":
            continue
        parsed.append(json.loads(body))
    return parsed


class _WebSearchAgent:
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
                            content="",
                            tool_calls=[
                                {"name": "web_search", "args": {"query": "Onyx"}, "id": "call-1"}
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
                            content=_WEB_SEARCH_RESULT,
                            tool_call_id="call-1",
                            name="web_search",
                        )
                    ]
                }
            },
        )


class _FetchWebpageAgent:
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
                            content="",
                            tool_calls=[
                                {
                                    "name": "fetch_webpage",
                                    "args": {"url": "https://onyx.app"},
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
                            content=_FETCH_RESULT,
                            tool_call_id="call-1",
                            name="fetch_webpage",
                        )
                    ]
                }
            },
        )


class _StreamingWebSearchAgent:
    """Mimics a provider that streams tool_call_chunks before the node's
    `updates` event reports the completed call — e.g. the first chunk
    carries only the tool name, with the query arriving in later chunks."""

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
                        {"name": "web_search", "args": "", "id": "call-1", "index": 0}
                    ],
                ),
                {},
            ),
        )
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {"name": None, "args": '{"query": "Onyx"}', "id": None, "index": 0}
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
                                {"name": "web_search", "args": {"query": "Onyx"}, "id": "call-1"}
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
                            content=_WEB_SEARCH_RESULT,
                            tool_call_id="call-1",
                            name="web_search",
                        )
                    ]
                }
            },
        )


class _FakeAssistantService:
    def __init__(self, agent):
        self._agent = agent

    async def get_graph_and_config(self, _agent_id):
        return "chatbot", {}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return self._agent


async def _fake_handle_input(_user_input, _agent, _user_id=None):
    return {"input": {"messages": []}, "config": {}}, uuid4()


@pytest.mark.asyncio
async def test_web_search_call_and_result_emit_search_tool_packets(monkeypatch):
    from service import AgentStreamService as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_WebSearchAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in agent_message_stream.message_generator(
            StreamInput(message="Onyx nedir"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    types = [p["type"] for p in packets]
    assert "search_tool_start" in types
    assert "search_tool_queries_delta" in types
    assert "search_tool_documents_delta" in types
    assert "custom_tool_start" not in types
    assert "custom_tool_delta" not in types

    queries_packet = next(p for p in packets if p["type"] == "search_tool_queries_delta")
    assert queries_packet["queries"] == ["Onyx"]

    docs_packet = next(p for p in packets if p["type"] == "search_tool_documents_delta")
    assert docs_packet["documents"][0]["document_id"] == "https://onyx.app"


@pytest.mark.asyncio
async def test_streamed_tool_call_chunks_do_not_leak_a_generic_tool_step(monkeypatch):
    """A provider reporting web_search via tool_call_chunks (name-then-args
    split across chunks, before the `updates` event completes the call) must
    still end up with search_tool_* packets only — no custom_tool_start
    should leak from the partial-args chunk, and the later `updates` event
    must not be skipped as an already-emitted duplicate."""
    from service import AgentStreamService as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_StreamingWebSearchAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in agent_message_stream.message_generator(
            StreamInput(message="Onyx nedir"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    types = [p["type"] for p in packets]
    assert "custom_tool_start" not in types
    assert "custom_tool_delta" not in types
    assert "search_tool_start" in types
    assert "search_tool_queries_delta" in types
    assert "search_tool_documents_delta" in types

    queries_packet = next(p for p in packets if p["type"] == "search_tool_queries_delta")
    assert queries_packet["queries"] == ["Onyx"]


@pytest.mark.asyncio
async def test_fetch_webpage_call_and_result_emit_open_url_packets(monkeypatch):
    from service import AgentStreamService as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_FetchWebpageAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in agent_message_stream.message_generator(
            StreamInput(message="onyx.app'i oku"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    types = [p["type"] for p in packets]
    assert "open_url_start" in types
    assert "open_url_urls" in types
    assert "open_url_documents" in types
    assert "custom_tool_start" not in types
    assert "custom_tool_delta" not in types

    docs_packet = next(p for p in packets if p["type"] == "open_url_documents")
    assert docs_packet["documents"][0]["link"] == "https://onyx.app"


class _FetchWebpageErrorAgent:
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
                            content="",
                            tool_calls=[
                                {
                                    "name": "fetch_webpage",
                                    "args": {"url": "https://example.com/404"},
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
                            content="Error fetching webpage: Client error '404 Not Found' for url 'https://example.com/404'",
                            tool_call_id="call-1",
                            name="fetch_webpage",
                        )
                    ]
                }
            },
        )


@pytest.mark.asyncio
async def test_fetch_webpage_error_streams_open_url_documents_with_error_cleanly(monkeypatch):
    from service import AgentStreamService as agent_message_stream

    monkeypatch.setattr(
        agent_message_stream.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_FetchWebpageErrorAgent()),
    )
    monkeypatch.setattr(agent_message_stream, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in agent_message_stream.message_generator(
            StreamInput(message="hatalı linki oku"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    types = [p["type"] for p in packets]
    assert "open_url_start" in types
    assert "open_url_urls" in types
    assert "open_url_documents" in types
    assert "custom_tool_start" not in types
    assert "custom_tool_delta" not in types

    docs_packet = next(p for p in packets if p["type"] == "open_url_documents")
    doc = docs_packet["documents"][0]
    assert doc["link"] == "https://example.com/404"
    assert doc["is_error"] is True
    assert "404 Not Found" in doc["error"]


@pytest.mark.asyncio
async def test_web_search_result_packets_carry_a_timestamp(monkeypatch):
    """The graph stage strip measures the "Web Araçları" node from the
    start/end packet timestamps. The start packet already carries one; the
    result packet must too, or the strip clamps the span to its 10ms floor
    live while a reload (which stamps both ends from the blob) shows it
    correctly."""
    from service import AgentStreamService as AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_WebSearchAgent()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="Onyx nedir"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    start = next(p for p in packets if p["type"] == "search_tool_start")
    docs = next(p for p in packets if p["type"] == "search_tool_documents_delta")
    assert isinstance(start.get("timestamp"), (int, float))
    assert isinstance(docs.get("timestamp"), (int, float))
    assert docs["timestamp"] >= start["timestamp"]


@pytest.mark.asyncio
async def test_fetch_webpage_result_packets_carry_a_timestamp(monkeypatch):
    """Same as above for the fetch_webpage (open_url) variant."""
    from service import AgentStreamService as AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_FetchWebpageAgent()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    chunks = [
        chunk
        async for chunk in AgentsRoute.message_generator(
            StreamInput(message="onyx.app'i oku"),
            agent_id="chatbot",
            user_id="user-1",
        )
    ]
    packets = _packets(chunks)

    start = next(p for p in packets if p["type"] == "open_url_start")
    docs = next(p for p in packets if p["type"] == "open_url_documents")
    assert isinstance(start.get("timestamp"), (int, float))
    assert isinstance(docs.get("timestamp"), (int, float))
    assert docs["timestamp"] >= start["timestamp"]
