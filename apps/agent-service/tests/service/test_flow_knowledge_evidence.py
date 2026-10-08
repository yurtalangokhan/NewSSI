"""Flow runs: retrieval-node evidence streams live, persists as a reference, and replays."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.knowledge_evidence.presenter import KnowledgeEvidencePresenter
from service.orchestration.agent_stream_service import _RunContext, _SseFramer, _stream_completed_messages
from service.reconstruction.flow_timeline import emit_flow_timeline_packets
from service.storage.document_progress_tracker import DocumentProgressTracker
from service.stream.flow_stage_tracker import _LiveStageTracker
from service.web_search.web_search_progress_tracker import WebSearchProgressTracker
from tests.service.evidence.conftest import THREAD_ID, InMemoryEvidenceStore, make_evidence

EVIDENCE_TOOL = "document_search"


def _ctx(store: InMemoryEvidenceStore) -> _RunContext:
    tp = SimpleNamespace(feed=lambda *_a, **_k: [], flush=list)
    tracker = _LiveStageTracker(final_node_ids={"answer"}, label_fn=lambda node_id: node_id)
    tracker.begin_stage("search-1", 1_000)
    nodes = {"search-1": {"id": "search-1", "type": "DocumentSearch"}}
    return _RunContext(
        agent=None,
        user_input=SimpleNamespace(message="q", stream_tokens=True, thread_id=str(THREAD_ID)),
        run_id="r1",
        start_time=0.0,
        framer=_SseFramer(tp, tracker, nodes),
        thinking_processor=tp,
        document_progress=DocumentProgressTracker(),
        web_search_progress=WebSearchProgressTracker(),
        stage_tracker=tracker,
        knowledge_evidence=KnowledgeEvidencePresenter(KnowledgeEvidenceHydrator(store), thread_id=str(THREAD_ID)),
    )


async def _packets(ctx: _RunContext, events: list[dict]) -> list[dict]:
    frames = [frame async for frame in _stream_completed_messages(ctx, events)]
    return [json.loads(f.strip()[6:]) for f in frames if f.strip().startswith("data: {")]


async def _stage_evidence_event(store: InMemoryEvidenceStore) -> tuple[dict, str]:
    evidence_id = str(await store.add(THREAD_ID, make_evidence(tool=EVIDENCE_TOOL)))
    event = {
        "type": "flow_stage_evidence",
        "node_id": "search-1",
        "evidence_id": evidence_id,
        "tool": EVIDENCE_TOOL,
        "query": "leave carry-over",
    }
    return event, evidence_id


@pytest.mark.asyncio
async def test_stage_evidence_streams_a_tool_step_tagged_with_its_stage() -> None:
    store = InMemoryEvidenceStore()
    ctx = _ctx(store)
    event, evidence_id = await _stage_evidence_event(store)

    start, delta = await _packets(ctx, [event])

    assert start["type"] == "custom_tool_start"
    assert start["tool_name"] == EVIDENCE_TOOL
    assert start["args"] == {"query": "leave carry-over"}
    assert delta["type"] == "custom_tool_delta"
    assert delta["response_type"] == "knowledge_retrieval"
    assert delta["evidence_id"] == evidence_id
    assert delta["data"] == make_evidence(tool=EVIDENCE_TOOL).model_dump(mode="json")
    assert start["call_id"] == delta["call_id"]
    assert {start["stage_node_id"], delta["stage_node_id"]} == {"search-1"}
    assert start["stage_key"] == delta["stage_key"]


@pytest.mark.asyncio
async def test_stage_evidence_is_kept_as_a_reference_in_the_persisted_timeline() -> None:
    store = InMemoryEvidenceStore()
    ctx = _ctx(store)
    event, evidence_id = await _stage_evidence_event(store)
    await _packets(ctx, [event])

    blob = ctx.stage_tracker.build_blob(None)
    (tool,) = blob["stages"][0]["tools"]

    assert tool["evidence_id"] == evidence_id
    assert tool["result_preview"] == ""
    assert [(e["event"], e.get("evidence_id")) for e in ctx.flow_stage_runs] == [
        ("tool_start", None),
        ("tool_end", evidence_id),
    ]


@pytest.mark.asyncio
async def test_stage_evidence_without_a_presenter_is_ignored() -> None:
    store = InMemoryEvidenceStore()
    ctx = _ctx(store)
    ctx.knowledge_evidence = None
    event, _ = await _stage_evidence_event(store)

    assert await _packets(ctx, [event]) == []


def test_timeline_replays_an_evidence_step_as_an_unhydrated_knowledge_packet() -> None:
    blob = {
        "stages": [
            {
                "stage_key": "search-1#1",
                "node_id": "search-1",
                "label": "Politika belgeleri",
                "order": 1,
                "iteration": 1,
                "started_at": 1000,
                "ended_at": 1400,
                "status": "done",
                "is_final": False,
                "steps": [
                    {
                        "kind": "tool",
                        "tool_name": EVIDENCE_TOOL,
                        "call_id": "search-1:e",
                        "args": {"query": "q"},
                        "started_at": 1100,
                        "ended_at": 1300,
                        "result_preview": "",
                        "evidence_id": "4f0c3f0e-0a55-4b39-9d2f-54c0a7b1c9e2",
                    }
                ],
            }
        ],
        "final_stage_key": None,
    }

    packets, _ = emit_flow_timeline_packets(blob)

    delta = next(p["obj"] for p in packets if p["obj"]["type"] == "custom_tool_delta")
    assert delta["response_type"] == "knowledge_retrieval"
    assert delta["evidence_id"] == "4f0c3f0e-0a55-4b39-9d2f-54c0a7b1c9e2"
    assert delta["data"] is None
    assert delta["timestamp"] == 1300
    assert delta["stage_node_id"] == "search-1"


def test_legacy_stage_events_replay_an_evidence_step_as_a_knowledge_packet() -> None:
    from service.chat.chat_history_reconstruction import _stage_timeline_packets

    evidence_id = "4f0c3f0e-0a55-4b39-9d2f-54c0a7b1c9e2"
    events = [
        {"event": "tool_start", "tool_name": EVIDENCE_TOOL, "call_id": "c", "args": {"query": "q"}, "timestamp": 1},
        {
            "event": "tool_end",
            "tool_name": EVIDENCE_TOOL,
            "call_id": "c",
            "data": "",
            "timestamp": 2,
            "stage_node_id": "search-1",
            "evidence_id": evidence_id,
        },
    ]

    packets = _stage_timeline_packets(events)

    delta = next(p["obj"] for p in packets if p["obj"]["type"] == "custom_tool_delta")
    assert delta["response_type"] == "knowledge_retrieval"
    assert delta["evidence_id"] == evidence_id
    assert delta["stage_node_id"] == "search-1"
    assert delta["timestamp"] == 2
