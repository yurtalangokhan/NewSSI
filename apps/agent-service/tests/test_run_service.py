"""Tests for SDK run streaming behavior."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from service.RunService import RunService


def _chat_model_stream_event(chunk):
    return {"event": "on_chat_model_stream", "run_id": "model-1", "data": {"chunk": chunk}}


async def _run_and_collect(agent, **overrides):
    service = RunService()
    cancel_event = asyncio.Event()
    kwargs = {
        "input_messages": [{"type": "human", "content": "merhaba"}],
        "config": {"configurable": {}},
        "thread_id": "thread-1",
        "run_id": "run-1",
        "stream_mode": ["values"],
        "user_id": "user-1",
    }
    kwargs.update(overrides)
    with (
        patch("service.RunService.register_run", return_value=cancel_event),
        patch("service.RunService.get_run_context", return_value=None),
        patch("service.RunService.unregister_run"),
    ):
        return [chunk async for chunk in service.event_generator(agent, **kwargs)]


def _payloads(chunks):
    return [json.loads(c.removeprefix("data: ").strip()) for c in chunks if c.startswith("data: {")]


class DummyAgent:
    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield {
            "event": "custom",
            "data": {
                "type": "long_term_memory_recall",
                "fact_count": 1,
                "memories": ["User likes tea"],
            },
        }
        yield {"event": "on_chain_end", "run_id": "run-1", "data": {"output": "done"}}


@pytest.mark.asyncio
async def test_event_generator_forwards_custom_ltm_event():
    service = RunService()
    cancel_event = asyncio.Event()

    with (
        patch("service.RunService.register_run", return_value=cancel_event),
        patch("service.RunService.get_run_context", return_value=None),
        patch("service.RunService.unregister_run"),
    ):
        chunks = [
            chunk
            async for chunk in service.event_generator(
                DummyAgent(),
                [{"type": "human", "content": "hello"}],
                config={"configurable": {}},
                thread_id="thread-1",
                run_id="run-1",
                stream_mode=["custom"],
                user_id="user-1",
            )
        ]

    first_payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert first_payload["type"] == "long_term_memory_recall"
    assert first_payload["fact_count"] == 1
    assert chunks[-1] == "data: [DONE]\n\n"


class RootFinalStateAgent:
    """Mirrors a real compiled LangGraph: nested sub-chains (prompt
    formatting) end with non-empty parent_ids and raw BaseMessage/dict
    output, then the graph's own root run ends with parent_ids=[] and the
    full state dict as output — what a user actually saw as a raw Python
    repr on screen before this was fixed."""

    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        # A nested prompt-formatting sub-chain finishing — must never reach
        # the client as a chat message.
        yield {
            "event": "on_chain_end",
            "run_id": "sub-1",
            "parent_ids": ["root-run"],
            "data": {"output": [SystemMessage(content="You are a helpful assistant.")]},
        }
        # The graph's own completion — the only on_chain_end that should
        # ever become a "message" event.
        yield {
            "event": "on_chain_end",
            "run_id": "root-run",
            "parent_ids": [],
            "data": {
                "output": {
                    "messages": [
                        HumanMessage(content="merhaba"),
                        AIMessage(content="Merhaba! Nasıl yardımcı olabilirim?"),
                    ],
                    "scratch": {},
                }
            },
        }


@pytest.mark.asyncio
async def test_event_generator_extracts_final_ai_text_from_root_state_only():
    service = RunService()
    cancel_event = asyncio.Event()

    with (
        patch("service.RunService.register_run", return_value=cancel_event),
        patch("service.RunService.get_run_context", return_value=None),
        patch("service.RunService.unregister_run"),
    ):
        chunks = [
            chunk
            async for chunk in service.event_generator(
                RootFinalStateAgent(),
                [{"type": "human", "content": "merhaba"}],
                config={"configurable": {}},
                thread_id="thread-1",
                run_id="run-1",
                stream_mode=["values"],
                user_id="user-1",
            )
        ]

    message_payloads = [
        json.loads(c.removeprefix("data: ").strip())
        for c in chunks
        if c.startswith("data: {")
        and json.loads(c.removeprefix("data: ").strip()).get("type") == "message"
    ]

    # Exactly one message event — the nested sub-chain's SystemMessage list
    # never leaks out as its own event.
    assert len(message_payloads) == 1
    assert message_payloads[0]["content"] == "Merhaba! Nasıl yardımcı olabilirim?"
    # Never the raw Python repr of the state dict or a message list.
    for chunk in chunks:
        assert "SystemMessage(" not in chunk
        assert "'messages':" not in chunk
        assert "HumanMessage(" not in chunk


class ReasoningThenAnswerAgent:
    """A reasoning-capable model's stream: a few chunks carrying only
    ``additional_kwargs.reasoning_content`` (no visible content), then
    chunks carrying the actual answer text."""

    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield _chat_model_stream_event(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Let"})
        )
        yield _chat_model_stream_event(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": " me think..."})
        )
        yield _chat_model_stream_event(AIMessageChunk(content="Hello"))
        yield _chat_model_stream_event(AIMessageChunk(content=" world"))


@pytest.mark.asyncio
async def test_event_generator_streams_reasoning_before_the_answer():
    chunks = await _run_and_collect(ReasoningThenAnswerAgent())
    payloads = _payloads(chunks)
    types = [p["type"] for p in payloads]

    assert types == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_delta",
        "reasoning_done",
        "token",
        "token",
    ]
    assert payloads[1]["reasoning"] == "Let"
    assert payloads[2]["reasoning"] == " me think..."
    assert payloads[4]["content"] == "Hello"
    assert payloads[5]["content"] == " world"


class PlainAnswerAgent:
    """A model with no reasoning capability — must not emit any
    reasoning_* events, matching pre-existing token-only behavior."""

    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield _chat_model_stream_event(AIMessageChunk(content="Hi"))
        yield _chat_model_stream_event(AIMessageChunk(content=" there"))


@pytest.mark.asyncio
async def test_event_generator_emits_no_reasoning_events_when_model_has_none():
    chunks = await _run_and_collect(PlainAnswerAgent())
    types = [p["type"] for p in _payloads(chunks)]

    assert "reasoning_start" not in types
    assert "reasoning_delta" not in types
    assert "reasoning_done" not in types
    assert types == ["token", "token"]


class ReasoningNeverFollowedByAnswerAgent:
    """The stream ends (error/cancel) while still "thinking" — reasoning_done
    must still be emitted so the UI's "Thinking…" block doesn't hang forever."""

    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield _chat_model_stream_event(
            AIMessageChunk(content="", additional_kwargs={"reasoning_content": "still going"})
        )


@pytest.mark.asyncio
async def test_event_generator_closes_dangling_reasoning_block_on_stream_end():
    chunks = await _run_and_collect(ReasoningNeverFollowedByAnswerAgent())
    types = [p["type"] for p in _payloads(chunks)]

    assert types == ["reasoning_start", "reasoning_delta", "reasoning_done"]


class ToolAndUsageAgent:
    """A run that calls one tool and finishes a model turn carrying
    ``usage_metadata`` — the raw material the flow playground needs for its
    tool-call blocks and its token/duration footer."""

    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield {
            "event": "on_tool_start",
            "run_id": "tool-abc",
            "name": "perform_search",
            "data": {"input": {"query": "Türksat tarihi", "search_mode": "Web"}},
        }
        yield {
            "event": "on_tool_end",
            "run_id": "tool-abc",
            "name": "perform_search",
            "data": {"output": [{"title": "Türksat - Vikipedi"}]},
        }
        yield _chat_model_stream_event(AIMessageChunk(content="Türksat 2004'te kuruldu."))
        yield {
            "event": "on_chat_model_end",
            "run_id": "model-1",
            "data": {
                "output": AIMessage(
                    content="Türksat 2004'te kuruldu.",
                    usage_metadata={
                        "input_tokens": 33800,
                        "output_tokens": 370,
                        "total_tokens": 34170,
                    },
                )
            },
        }


@pytest.mark.asyncio
async def test_event_generator_emits_tool_usage_and_duration_for_playground_runs():
    chunks = await _run_and_collect(
        ToolAndUsageAgent(),
        config={"configurable": {"run_kind": "playground"}},
    )
    payloads = _payloads(chunks)
    by_type = {p["type"]: p for p in payloads}

    assert by_type["tool_call_start"]["call_id"] == "tool-abc"
    assert by_type["tool_call_start"]["name"] == "perform_search"
    assert by_type["tool_call_start"]["input"] == {
        "query": "Türksat tarihi",
        "search_mode": "Web",
    }

    assert by_type["tool_call_end"]["call_id"] == "tool-abc"
    assert by_type["tool_call_end"]["output"] == [{"title": "Türksat - Vikipedi"}]

    assert by_type["usage"]["input_tokens"] == 33800
    assert by_type["usage"]["output_tokens"] == 370
    assert by_type["usage"]["total_tokens"] == 34170

    assert isinstance(by_type["run_end"]["duration_ms"], int)
    # run_end lands right before the [DONE] sentinel.
    assert [p["type"] for p in payloads][-1] == "run_end"
    assert chunks[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_event_generator_suppresses_rich_events_for_sdk_runs():
    """RunRoute (SDK) never sets ``run_kind`` — its stream must stay exactly
    as it was: no tool_call_*, usage, or run_end events."""
    chunks = await _run_and_collect(
        ToolAndUsageAgent(),
        config={"configurable": {}},
    )
    types = {p["type"] for p in _payloads(chunks)}

    assert "tool_call_start" not in types
    assert "tool_call_end" not in types
    assert "usage" not in types
    assert "run_end" not in types
    assert chunks[-1] == "data: [DONE]\n\n"
