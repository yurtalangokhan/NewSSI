"""Live SSE stream and reload reconstruction must produce the same per-stage
step sequence — same order, same number of thinking blocks, same tool packets.

Regression for the "refresh changes the transcript" bug: a stage's second
thinking block slid into the next stage, web searches lost their search
widget, and the ReAct stage's tool/thinking order flipped, because the
persisted blob was a per-stage *aggregate* (one merged reasoning string, one
merged output string, a flat tool list) rather than an ordered step log.
"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from models.chat import StreamInput
from service.flow_timeline_reconstruction import emit_flow_timeline_packets
from tests.test_message_generator_flow_stage_events import (
    _fake_handle_input,
    _FakeAssistantService,
    _FakeFlowAgent,
    _mchunk,
)

_SEARCH_RESULT = "TITLE: Llama 3.1\nURL: https://example.com/llama\nSNIPPET: 128K context window."


def _calls(cid, *calls):
    """A sub-graph model node returning its completed tool calls. web_search
    starts are deferred to exactly this `updates` event (its streamed chunks
    carry fragmented args), so this is the only path that opens one."""
    return (
        "updates",
        {
            "model": {
                "messages": [
                    AIMessage(
                        content="",
                        id=cid,
                        tool_calls=[{"name": n, "args": a, "id": i} for n, a, i in calls],
                    )
                ]
            }
        },
    )


def _results(*results):
    """A sub-graph tools node returning its ToolMessages."""
    return (
        "updates",
        {
            "tools": {
                "messages": [ToolMessage(content=c, name=n, tool_call_id=i) for n, c, i in results]
            }
        },
    )


class _InterleavedFlowAgent(_FakeFlowAgent):
    """A realistic deep-research run.

    research: think -> web_search -> think -> web_search -> output
    react:    think -> run_python -> think -> run_python -> output(final)

    Each node also re-delivers its accumulated message list through the
    `updates` stream when it returns — exactly what a real compiled graph
    does, and the source of the duplicate tool_end events seen in production.
    """

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"node-react"}

    async def aget_state(self, *args, **kwargs):
        class _State:
            values = {
                "messages": [
                    HumanMessage(content="q", id="h1"),
                    AIMessage(content="FINAL ANSWER", id="ai-final"),
                ]
            }

        return _State()

    async def astream(self, *args, **kwargs):
        searches = [
            ("web_search", _SEARCH_RESULT, "c1"),
            ("web_search", _SEARCH_RESULT, "c2"),
        ]

        # ---- research stage -------------------------------------------------
        yield ("debug", {"type": "task", "payload": {"id": "r", "name": "node-research"}})
        yield _mchunk(reasoning="First I plan the searches.", cid="r1", ns="r:a|model:x")
        yield _calls("r2", ("web_search", {"query": "llama context"}, "c1"))
        yield _results(searches[0])

        yield _mchunk(reasoning="Now I need one more source.", cid="r3", ns="r:a|model:x")
        yield _calls("r4", ("web_search", {"query": "deepseek context"}, "c2"))
        yield _results(searches[1])

        yield _mchunk("RESEARCH BRIEFING", cid="r5", ns="r:a|model:x")
        # The node returns: its whole accumulated message list comes back.
        yield (
            "updates",
            {
                "node-research": {
                    "messages": [
                        ToolMessage(content=c, name=n, tool_call_id=i) for n, c, i in searches
                    ]
                }
            },
        )
        yield ("debug", {"type": "task_result", "payload": {"id": "r", "name": "node-research"}})

        # ---- react stage (final) -------------------------------------------
        yield ("debug", {"type": "task", "payload": {"id": "k", "name": "node-react"}})
        yield _mchunk(reasoning="Let me compute the average.", cid="k1", ns="k:b|model:y")
        yield _calls("k2", ("run_python", {"code": "print(1)"}, "c3"))
        yield _results(("run_python", "SyntaxError", "c3"))

        yield _mchunk(reasoning="Syntax error, fixing it.", cid="k3", ns="k:b|model:y")
        yield _calls("k4", ("run_python", {"code": "print(2)"}, "c4"))
        yield _results(("run_python", "128000", "c4"))

        yield _mchunk("FINAL ANSWER", cid="k5", ns="k:b|model:y")
        yield (
            "updates",
            {
                "node-react": {
                    "messages": [
                        *[ToolMessage(content=c, name=n, tool_call_id=i) for n, c, i in searches],
                        ToolMessage(content="SyntaxError", name="run_python", tool_call_id="c3"),
                        ToolMessage(content="128000", name="run_python", tool_call_id="c4"),
                    ]
                }
            },
        )
        yield ("debug", {"type": "task_result", "payload": {"id": "k", "name": "node-react"}})


async def _run_live(monkeypatch, agent) -> tuple[list[dict], dict]:
    """Drive one live SSE run, returning its packets and the persisted metadata."""
    import controller
    import service.StoreService as StoreService
    from service import AgentStreamService as AgentsRoute

    captured: dict = {}

    async def _fake_get_thread(_tid):
        return {"metadata": {}}

    async def _fake_update(_tid, updates, update_timestamp=True):
        captured.update(updates.get("metadata", {}))
        return {}

    class _FakeIdController:
        def __init__(self, *_a, **_k):
            pass

        async def get_chat_session(self, _tid):
            return {"messages": []}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)
    monkeypatch.setattr(controller, "ChatController", _FakeIdController)
    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService, "get_instance", lambda: _FakeAssistantService(agent)
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    live = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="q", thread_id="t1"), agent_id="flow-def-1", user_id="u1"
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            live.append(json.loads(body))
    return live, captured


_STEP_TYPES = {
    "reasoning_start": "think",
    "search_tool_start": "search",
    "custom_tool_start": "tool",
    "flow_stage_output_delta": "output",
}


def _collect(packets, type_of, key_of) -> dict[str, list[str]]:
    """Ordered step kinds per stage_key.

    Consecutive output deltas collapse into one entry: live streams the
    stage's text in as many chunks as the model sent, a reload replays it
    whole, and both render as a single output block.
    """
    steps: dict[str, list[str]] = {}
    for p in packets:
        kind = _STEP_TYPES.get(type_of(p).get("type"))
        key = key_of(p)
        if not kind or not key:
            continue
        seq = steps.setdefault(key, [])
        if kind == "output" and seq and seq[-1] == "output":
            continue
        seq.append(kind)
    return steps


def _live_steps(packets: list[dict]) -> dict[str, list[str]]:
    return _collect(packets, lambda p: p, lambda p: p.get("stage_key"))


def _reload_steps(packets: list[dict]) -> dict[str, list[str]]:
    return _collect(packets, lambda p: p["obj"], lambda p: p["placement"].get("stage_key"))


@pytest.mark.asyncio
async def test_reload_preserves_step_order_within_each_stage(monkeypatch):
    """The blob must replay each stage's steps in their original order."""
    live, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())
    blob = captured["flow_timelines"]["ai-final"]
    reload_packets, _ = emit_flow_timeline_packets(blob)

    assert _reload_steps(reload_packets) == _live_steps(live)
    assert _reload_steps(reload_packets) == {
        "node-research#1": ["think", "search", "think", "search", "output"],
        "node-react#1": ["think", "tool", "think", "tool"],
    }

    # The folded stage's text survives whole, not just in the right position.
    def _text(packets, type_of, key_of):
        return "".join(
            type_of(p)["content"]
            for p in packets
            if type_of(p).get("type") == "flow_stage_output_delta"
            and key_of(p) == "node-research#1"
        )

    assert (
        _text(reload_packets, lambda p: p["obj"], lambda p: p["placement"]["stage_key"])
        == _text(live, lambda p: p, lambda p: p.get("stage_key"))
        == "RESEARCH BRIEFING"
    )


@pytest.mark.asyncio
async def test_each_thinking_block_stays_its_own_block(monkeypatch):
    """Two separate thinking blocks must not merge into one run-on block."""
    _, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())
    blob = captured["flow_timelines"]["ai-final"]
    reload_packets, _ = emit_flow_timeline_packets(blob)

    research_thinks = [
        p["obj"]["reasoning"]
        for p in reload_packets
        if p["obj"]["type"] == "reasoning_delta"
        and p["placement"]["stage_key"] == "node-research#1"
    ]
    assert research_thinks == ["First I plan the searches.", "Now I need one more source."]


@pytest.mark.asyncio
async def test_reasoning_is_not_recorded_onto_two_stages(monkeypatch):
    """A stage's reasoning must not also be appended to its neighbour."""
    _, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())
    stages = captured["flow_timelines"]["ai-final"]["stages"]
    texts = {s["stage_key"]: s.get("reasoning_text") or "" for s in stages}

    assert "Syntax error, fixing it." not in texts["node-research#1"]
    assert "First I plan the searches." not in texts["node-react#1"]


@pytest.mark.asyncio
async def test_web_search_results_are_recorded_for_replay(monkeypatch):
    """web_search must reach the tracker so a reload can rebuild the search
    widget instead of an empty generic tool row."""
    live, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())
    stages = captured["flow_timelines"]["ai-final"]["stages"]
    research = next(s for s in stages if s["stage_key"] == "node-research#1")

    searches = [t for t in research["tools"] if t["tool_name"] == "web_search"]
    assert len(searches) == 2
    for tool in searches:
        assert tool["ended_at"] is not None

    # A reload replays the same search widget packets the live run sent —
    # queries and hits included — not a bare, unfinished tool row.
    reload_packets, _ = emit_flow_timeline_packets(captured["flow_timelines"]["ai-final"])

    def _widget(packets, type_of, key_of):
        return [
            {k: v for k, v in type_of(p).items() if k in ("type", "call_id", "queries")}
            for p in packets
            if str(type_of(p).get("type", "")).startswith("search_tool_")
            and key_of(p) == "node-research#1"
        ]

    assert _widget(
        reload_packets, lambda p: p["obj"], lambda p: p["placement"]["stage_key"]
    ) == _widget(live, lambda p: p, lambda p: p.get("stage_key"))
    docs = [
        p["obj"]["documents"]
        for p in reload_packets
        if p["obj"]["type"] == "search_tool_documents_delta"
    ]
    assert docs and all(d for d in docs), "search hits were lost on reload"


@pytest.mark.asyncio
async def test_web_tool_strip_span_matches_between_live_and_reload(monkeypatch):
    """The graph stage strip measures a web tool node from its start/end
    packet timestamps. Live, the result packet used to ship without one, so
    the strip clamped the span to its 10ms floor while a reload — which
    stamps both ends from the blob — showed the real duration. Both ends of
    the live widget must now carry a timestamp, and it must equal the span a
    reload replays for the same call."""
    live, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())

    live_span: dict[str, list[int]] = {}
    for p in live:
        if p.get("type") == "search_tool_start":
            assert isinstance(p.get("timestamp"), (int, float))
            live_span.setdefault(p["call_id"], [None, None])[0] = p["timestamp"]
        elif p.get("type") == "search_tool_documents_delta":
            assert isinstance(p.get("timestamp"), (int, float)), (
                "web search result packet lost its timestamp — strip can't measure the node live"
            )
            live_span.setdefault(p["call_id"], [None, None])[1] = p["timestamp"]

    assert live_span and all(a is not None and b is not None for a, b in live_span.values())

    reload_packets, _ = emit_flow_timeline_packets(captured["flow_timelines"]["ai-final"])
    reload_span: dict[str, list[int]] = {}
    for p in reload_packets:
        obj = p["obj"]
        if obj.get("type") == "search_tool_start":
            reload_span.setdefault(obj["call_id"], [None, None])[0] = obj["timestamp"]
        elif obj.get("type") == "search_tool_documents_delta":
            reload_span.setdefault(obj["call_id"], [None, None])[1] = obj["timestamp"]

    assert reload_span == live_span


@pytest.mark.asyncio
async def test_duplicate_tool_ends_do_not_corrupt_timings(monkeypatch):
    """A node re-delivering its message list must not re-close tools that
    already ended, which would stretch their duration to the node's end."""
    live, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())

    # The live stream must not report the same tool result twice...
    results = [
        p.get("call_id")
        for p in live
        if p.get("type") == "custom_tool_delta" and p.get("response_type") == "tool_result"
    ]
    assert len(results) == len(set(results)), f"duplicate tool results: {results}"

    # ...nor re-close a web search under a stage that never ran it.
    searches_by_stage: dict[str, list[str]] = {}
    for p in live:
        if p.get("type") == "search_tool_documents_delta":
            searches_by_stage.setdefault(p.get("stage_key"), []).append(p["call_id"])
    assert searches_by_stage == {"node-research#1": ["c1", "c2"]}

    # And the blob's end time for each tool is the one the live stream used,
    # not a later stage's boundary.
    live_ends = {
        p["call_id"]: p["timestamp"]
        for p in live
        if p.get("type") == "custom_tool_delta" and p.get("response_type") == "tool_result"
    }
    stages = captured["flow_timelines"]["ai-final"]["stages"]
    react = next(s for s in stages if s["stage_key"] == "node-react#1")
    assert {t["call_id"]: t["ended_at"] for t in react["tools"]} == live_ends


@pytest.mark.asyncio
async def test_reload_still_renders_the_graph_stage_strip(monkeypatch):
    """A blob-backed run must replay its graph_stage_* events too.

    Without them the strip has no stage timings to show: it falls back to the
    flow definition and paints every stage grey/pending, while the blob's own
    tool packets — belonging to no stage — float up as top-level entries.
    """
    from service.ChatHistoryReconstruction import ReconstructionState, _emit_flow_blob_turn

    _, captured = await _run_live(monkeypatch, _InterleavedFlowAgent())

    state = ReconstructionState(
        flow_stage_timelines=captured["flow_stage_timelines"],
        flow_timelines=captured["flow_timelines"],
    )
    packets_2d: list[list[dict]] = []
    _emit_flow_blob_turn(
        state,
        captured["flow_timelines"]["ai-final"],
        [],
        packets_2d,
        "chat-1",
        stage_events=captured["flow_stage_timelines"]["ai-final"],
    )

    turn = packets_2d[0]
    stage_names = [p["obj"]["stage_name"] for p in turn if p["obj"]["type"] == "graph_stage_start"]
    assert stage_names == ["node-research", "node-react"]
    assert [p["obj"]["stage_name"] for p in turn if p["obj"]["type"] == "graph_stage_end"] == [
        "node-research",
        "node-react",
    ]


def test_repair_legacy_tools_recovers_web_searches_from_the_event_log():
    """Runs recorded before the blob kept `steps` never stored a web tool's
    result or end time. The event log did — so the widget and the real
    duration come back from there."""
    from service.flow_timeline_reconstruction import (
        emit_flow_timeline_packets,
        repair_legacy_tools,
    )

    blob = {
        "stages": [
            {
                "stage_key": "R#1",
                "node_id": "R",
                "label": "R",
                "order": 1,
                "iteration": 1,
                "started_at": 100,
                "ended_at": 900,
                "status": "done",
                "is_final": False,
                "reasoning_text": "thinking",
                "output_text": "briefing",
                # What the old writer produced: opened, never closed.
                "tools": [
                    {
                        "tool_name": "web_search",
                        "call_id": "c1",
                        "args": {"query": "llama"},
                        "started_at": 200,
                        "ended_at": None,
                        "result_preview": "",
                    }
                ],
            }
        ],
        "final_stage_key": None,
    }
    events = [
        {
            "event": "tool_start",
            "tool_name": "web_search",
            "call_id": "c1",
            "args": {"query": "llama"},
            "timestamp": 200,
        },
        {
            "event": "tool_end",
            "tool_name": "web_search",
            "call_id": "c1",
            "data": _SEARCH_RESULT,
            "timestamp": 500,
        },
        # The repeat every old log carries: must not become the real end.
        {
            "event": "tool_end",
            "tool_name": "web_search",
            "call_id": "c1",
            "data": _SEARCH_RESULT,
            "timestamp": 880,
        },
    ]

    tool = repair_legacy_tools(blob, events)["stages"][0]["tools"][0]
    assert tool["ended_at"] == 500
    assert [p["type"] for p in tool["web_packets"]] == [
        "search_tool_start",
        "search_tool_queries_delta",
        "search_tool_documents_delta",
    ]

    packets, _ = emit_flow_timeline_packets(repair_legacy_tools(blob, events))
    hits = next(p["obj"] for p in packets if p["obj"]["type"] == "search_tool_documents_delta")
    assert hits["documents"][0]["link"] == "https://example.com/llama"


def test_repair_legacy_tools_leaves_a_steps_blob_alone():
    """Blobs that recorded their own ordering are already correct."""
    from service.flow_timeline_reconstruction import repair_legacy_tools

    blob = {"stages": [{"stage_key": "R#1", "steps": [], "tools": []}]}
    events = [
        {
            "event": "tool_start",
            "tool_name": "web_search",
            "call_id": "c1",
            "args": {},
            "timestamp": 1,
        }
    ]
    assert repair_legacy_tools(blob, events) is blob
