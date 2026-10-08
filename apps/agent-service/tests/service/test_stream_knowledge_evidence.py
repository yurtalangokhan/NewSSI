"""Live stream: a knowledge tool result streams as a hydrated knowledge_retrieval delta."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.knowledge_evidence.presenter import KnowledgeEvidencePresenter
from service.knowledge_evidence.references import EVIDENCE_ARTIFACT_KEY
from service.orchestration.agent_stream_service import _RunContext, _SseFramer, _stream_completed_messages
from service.storage.document_progress_tracker import DocumentProgressTracker
from service.web_search.web_search_progress_tracker import WebSearchProgressTracker
from tests.service.evidence.conftest import THREAD_ID, InMemoryEvidenceStore, make_evidence


def _ctx(store: InMemoryEvidenceStore) -> _RunContext:
    tp = SimpleNamespace(feed=lambda *_a, **_k: [], flush=list)
    return _RunContext(
        agent=None,
        user_input=SimpleNamespace(message="q", stream_tokens=True, thread_id=str(THREAD_ID)),
        run_id="r1",
        start_time=0.0,
        framer=_SseFramer(tp, None, {}),
        thinking_processor=tp,
        document_progress=DocumentProgressTracker(),
        web_search_progress=WebSearchProgressTracker(),
        stage_tracker=None,
        knowledge_evidence=KnowledgeEvidencePresenter(KnowledgeEvidenceHydrator(store), thread_id=str(THREAD_ID)),
    )


async def _deltas(ctx: _RunContext, messages) -> list[dict]:
    frames = [frame async for frame in _stream_completed_messages(ctx, messages)]
    packets = [json.loads(f.strip()[6:]) for f in frames if f.strip().startswith("data: {")]
    return [packet for packet in packets if packet.get("type") == "custom_tool_delta"]


@pytest.mark.asyncio
async def test_knowledge_tool_result_streams_its_evidence() -> None:
    store = InMemoryEvidenceStore()
    evidence_id = await store.add(THREAD_ID, make_evidence())
    message = ToolMessage(
        content="[1] (a.pdf)\nUnused leave carries over.",
        name="database_search",
        tool_call_id="call-1",
        artifact={EVIDENCE_ARTIFACT_KEY: str(evidence_id)},
    )

    (delta,) = await _deltas(_ctx(store), [message])

    assert delta["response_type"] == "knowledge_retrieval"
    assert delta["evidence_id"] == str(evidence_id)
    assert delta["data"] == make_evidence().model_dump(mode="json")
    assert delta["call_id"] == "call-1"
    assert delta["tool_name"] == "database_search"
    assert isinstance(delta["timestamp"], int)


@pytest.mark.asyncio
async def test_ordinary_tool_result_is_unchanged() -> None:
    message = ToolMessage(content="4", name="calculator", tool_call_id="call-2")

    (delta,) = await _deltas(_ctx(InMemoryEvidenceStore()), [message])

    assert delta["response_type"] == "tool_result"
    assert delta["data"] == "4"
