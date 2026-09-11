"""`ask_user` must not also stream as a generic tool row.

It has its own card (the `user_clarification` packet from the interrupt
seam). A `custom_tool_start` / `custom_tool_delta` for it as well is the
live twin of reconstruction's E4 double-draw: the generic row lands first
in the turn group and steals `UserClarificationRenderer`'s slot, so the
card never renders — exactly the "ask_user tamamlandı, no question" bug.

Same exemption the document tools already have.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from service.AgentStreamService import (
    _RunContext,
    _SseFramer,
    _stream_completed_messages,
    _stream_token_events,
)
from service.DocumentProgressTracker import DocumentProgressTracker
from service.WebSearchProgressTracker import WebSearchProgressTracker


def _ctx():
    tp = SimpleNamespace(feed=lambda *_a, **_k: [], flush=lambda: [])
    return _RunContext(
        agent=None,
        user_input=SimpleNamespace(message="rapor hazırla", stream_tokens=True, thread_id="t"),
        run_id="r1",
        start_time=0.0,
        framer=_SseFramer(tp, None, {}),
        thinking_processor=tp,
        document_progress=DocumentProgressTracker(),
        web_search_progress=WebSearchProgressTracker(),
        stage_tracker=None,
    )


async def _frames(messages):
    out = []
    async for f in _stream_completed_messages(_ctx(), messages):
        out.append(f)
    types = []
    for f in out:
        s = f.strip()
        if s.startswith("data: ") and s != "data: [DONE]":
            try:
                types.append(json.loads(s[6:]).get("type"))
            except json.JSONDecodeError:
                pass
    return types


_ASK_CALL = {
    "name": "ask_user",
    "args": {"questions": [{"question": "q", "header": "H", "options": [{"label": "a"}]}]},
    "id": "ask-1",
}


@pytest.mark.asyncio
async def test_an_ask_user_tool_call_emits_no_custom_tool_start():
    types = await _frames([AIMessage(content="", tool_calls=[_ASK_CALL])])
    assert "custom_tool_start" not in types


@pytest.mark.asyncio
async def test_an_ask_user_tool_result_emits_no_custom_tool_delta():
    types = await _frames(
        [ToolMessage(content="Hedef kitle: Yönetim", name="ask_user", tool_call_id="ask-1")]
    )
    assert "custom_tool_delta" not in types


@pytest.mark.asyncio
async def test_an_ordinary_tool_call_still_emits_a_custom_tool_start():
    """Control: the exemption is `ask_user`-specific, not a blanket mute."""
    other = {"name": "get_weather", "args": {"city": "x"}, "id": "w-1"}
    types = await _frames([AIMessage(content="", tool_calls=[other])])
    assert "custom_tool_start" in types


async def _token_frame_types(chunk):
    out = []
    async for f in _stream_token_events(_ctx(), (chunk, {"tags": []}), "messages"):
        out.append(f)
    types = []
    for f in out:
        s = f.strip()
        if s.startswith("data: ") and s != "data: [DONE]":
            try:
                types.append(json.loads(s[6:]).get("type"))
            except json.JSONDecodeError:
                pass
    return types


@pytest.mark.asyncio
async def test_a_streamed_ask_user_tool_call_chunk_emits_no_custom_tool_start():
    """The path a real (token-streaming) model actually hits — the bug's home."""
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "ask_user", "args": "", "id": "ask-1", "index": 0}],
    )
    assert "custom_tool_start" not in await _token_frame_types(chunk)


@pytest.mark.asyncio
async def test_a_streamed_ordinary_tool_call_chunk_still_emits_a_custom_tool_start():
    chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "get_weather", "args": "", "id": "w-1", "index": 0}],
    )
    assert "custom_tool_start" in await _token_frame_types(chunk)
