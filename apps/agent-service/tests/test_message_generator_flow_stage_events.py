"""graph_stage_start/graph_stage_end for FlowAgent-backed chat personas.

The flow editor's Playground already shows live per-step status on canvas
cards via RunService's astream_events-based tracker. The general chat
stream uses a different LangGraph API (astream(stream_mode=[...])) and had
no equivalent — this adds it via LangGraph's "debug" stream mode, which
reports each node's start ("task") and end ("task_result") with the node's
real LangGraph name, which for a FlowAgent's compiled graph always equals
the flow canvas node id (flow_builder.py: graph.add_node(node.id, ...))."""

import json

import pytest
from langchain_core.messages import AIMessageChunk

from agents.flow_agent import FlowAgent
from models.chat import StreamInput


class _FakeFlowAgent(FlowAgent):
    """A FlowAgent stand-in whose astream() emits debug task/task_result
    events directly, without compiling a real graph."""

    def __init__(self) -> None:
        super().__init__(flow_spec=None, definition_id="fake-def")

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "debug",
            {"type": "task", "payload": {"id": "t1", "name": "ChatInput-1"}},
        )
        yield (
            "debug",
            {
                "type": "task_result",
                "payload": {"id": "t1", "name": "ChatInput-1", "result": {}},
            },
        )
        yield (
            "debug",
            {"type": "task", "payload": {"id": "t2", "name": "OllamaModel-1"}},
        )
        yield ("messages", (AIMessageChunk(id="call-1", content="Merhaba"), {}))
        yield (
            "debug",
            {
                "type": "task_result",
                "payload": {"id": "t2", "name": "OllamaModel-1", "result": {}},
            },
        )


class _NonFlowAgent:
    """A plain DynamicAgent-like agent: must never emit graph_stage_* even
    if it happens to see a debug event (defense against a future caller
    adding "debug" to some other agent's stream_mode list)."""

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        yield (
            "debug",
            {"type": "task", "payload": {"id": "t1", "name": "supervisor"}},
        )


class _FakeAssistantService:
    def __init__(self, agent) -> None:
        self._agent = agent

    async def get_graph_and_config(self, _agent_id):
        return "flow-def-1", {}

    async def get_configured_agent(self, _agent_id, _agent_config):
        return self._agent


async def _fake_handle_input(_user_input, _agent, _user_id=None):
    return {"input": {"messages": []}, "config": {}}, "run-1"


async def _run(monkeypatch, agent) -> list[dict]:
    from service import AgentStreamService as AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)

    packets = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="merhaba"),
        agent_id="flow-def-1",
        user_id="user-1",
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            packets.append(json.loads(body))
    return packets


@pytest.mark.asyncio
async def test_each_node_gets_a_start_and_end_event(monkeypatch):
    packets = await _run(monkeypatch, _FakeFlowAgent())

    starts = [p for p in packets if p["type"] == "graph_stage_start"]
    ends = [p for p in packets if p["type"] == "graph_stage_end"]

    assert [p["stage_name"] for p in starts] == ["ChatInput-1", "OllamaModel-1"]
    assert [p["stage_name"] for p in ends] == ["ChatInput-1", "OllamaModel-1"]


@pytest.mark.asyncio
async def test_stage_events_carry_a_numeric_timestamp(monkeypatch):
    packets = await _run(monkeypatch, _FakeFlowAgent())
    stage_packets = [p for p in packets if p["type"] in ("graph_stage_start", "graph_stage_end")]
    assert stage_packets
    for p in stage_packets:
        assert isinstance(p["timestamp"], int)


class _FlowAgentWithFinalMessage(_FakeFlowAgent):
    """Reports a real final AI message id from aget_state, so the post-stream
    timeline persistence has something to key on."""

    async def aget_state(self, *args, **kwargs):
        from langchain_core.messages import AIMessage, HumanMessage

        class _State:
            values = {
                "messages": [
                    HumanMessage(content="merhaba", id="h1"),
                    AIMessage(content="Merhaba", id="ai-final-1"),
                ]
            }

        return _State()


class _FakeIdController:
    """Stands in for the ChatController the post-stream block uses to resolve
    real message ids — keeps that path off the real async DB (a live pool
    bound to the test event loop poisons later TestClient(app) tests)."""

    def __init__(self, *_a, **_k):
        pass

    async def get_chat_session(self, _thread_id):
        return {"messages": []}


async def _run_with_thread(monkeypatch, agent, thread_id="thread-1"):
    import controller
    from service import AgentStreamService as AgentsRoute

    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(agent),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)
    monkeypatch.setattr(controller, "ChatController", _FakeIdController)

    packets = []
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="merhaba", thread_id=thread_id),
        agent_id="flow-def-1",
        user_id="user-1",
    ):
        body = chunk.removeprefix("data: ").strip()
        if body and body != "[DONE]" and not chunk.startswith(":"):
            packets.append(json.loads(body))
    return packets


@pytest.mark.asyncio
async def test_flow_stage_timeline_is_persisted_to_thread_metadata(monkeypatch):
    import service.StoreService as StoreService

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {"persona_id": 3}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates, update_timestamp))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    await _run_with_thread(monkeypatch, _FlowAgentWithFinalMessage())

    assert len(writes) == 1
    thread_id, updates, update_timestamp = writes[0]
    assert thread_id == "thread-1"
    assert update_timestamp is False
    timelines = updates["metadata"]["flow_stage_timelines"]
    assert list(timelines) == ["ai-final-1"]
    events = timelines["ai-final-1"]
    assert [(e["stage_name"], e["event"]) for e in events] == [
        ("ChatInput-1", "start"),
        ("ChatInput-1", "end"),
        ("OllamaModel-1", "start"),
        ("OllamaModel-1", "end"),
    ]
    assert all(isinstance(e["timestamp"], int) for e in events)


@pytest.mark.asyncio
async def test_flow_stage_timeline_persistence_prunes_to_the_cap(monkeypatch):
    import service.StoreService as StoreService
    from service import AgentStreamService as AgentsRoute

    existing = {f"old-{i}": [] for i in range(AgentsRoute.STAGE_TIMELINE_MAX_KEPT + 5)}
    writes: list[dict] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {"flow_stage_timelines": dict(existing)}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append(updates)
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    await _run_with_thread(monkeypatch, _FlowAgentWithFinalMessage())

    timelines = writes[0]["metadata"]["flow_stage_timelines"]
    assert len(timelines) == AgentsRoute.STAGE_TIMELINE_MAX_KEPT
    assert "ai-final-1" in timelines  # the newest entry is always kept


@pytest.mark.asyncio
async def test_non_flow_agent_never_persists_a_stage_timeline(monkeypatch):
    import service.StoreService as StoreService

    called = False

    async def _fake_update(*_a, **_k):
        nonlocal called
        called = True

    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)
    monkeypatch.setattr(StoreService, "get_thread_from_store", lambda *_a, **_k: _async_none())

    await _run_with_thread(monkeypatch, _NonFlowAgent())
    assert called is False


@pytest.mark.asyncio
async def test_stream_still_completes_when_timeline_persistence_fails(monkeypatch):
    import controller
    import service.StoreService as StoreService
    from service import AgentStreamService as AgentsRoute

    async def _boom_get_thread(_thread_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(StoreService, "get_thread_from_store", _boom_get_thread)
    monkeypatch.setattr(controller, "ChatController", _FakeIdController)

    saw_done = False
    monkeypatch.setattr(
        AgentsRoute.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_FlowAgentWithFinalMessage()),
    )
    monkeypatch.setattr(AgentsRoute, "_handle_input", _fake_handle_input)
    async for chunk in AgentsRoute.message_generator(
        StreamInput(message="merhaba", thread_id="thread-1"),
        agent_id="flow-def-1",
        user_id="user-1",
    ):
        if chunk.strip() == "data: [DONE]":
            saw_done = True
    assert saw_done is True


async def _async_none():
    return None


@pytest.mark.asyncio
async def test_stage_start_precedes_its_own_stage_end(monkeypatch):
    packets = await _run(monkeypatch, _FakeFlowAgent())
    types_and_names = [
        (p["type"], p["stage_name"])
        for p in packets
        if p["type"] in ("graph_stage_start", "graph_stage_end")
    ]
    assert types_and_names.index(("graph_stage_start", "OllamaModel-1")) < types_and_names.index(
        ("graph_stage_end", "OllamaModel-1")
    )


@pytest.mark.asyncio
async def test_non_flow_agents_never_emit_stage_events(monkeypatch):
    packets = await _run(monkeypatch, _NonFlowAgent())

    assert not any(p["type"].startswith("graph_stage_") for p in packets)


class _FakeFlowAgentWithSubgraphMessages(FlowAgent):
    """A FlowAgent whose ReActAgent node is a subgraph that reports its own
    messages once it returns — the "updates" event this produces used to
    also trip the generic custom_step_start mechanism (designed for classic
    DynamicAgent stages), surfacing a raw canvas node id like
    "[step] ReActAgent-f296f72f" as its own confusing timeline card,
    redundant with graph_stage_start/end's own (better labeled) progress."""

    def __init__(self) -> None:
        super().__init__(flow_spec=None, definition_id="fake-def")

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        from langchain_core.messages import AIMessage

        yield (
            "updates",
            {"ReActAgent-f296f72f": {"messages": [AIMessage(id="answer-1", content="Hazır.")]}},
        )


@pytest.mark.asyncio
async def test_flow_agent_nodes_never_emit_the_generic_custom_step_start(monkeypatch):
    packets = await _run(monkeypatch, _FakeFlowAgentWithSubgraphMessages())

    assert not any(p["type"] == "custom_step_start" for p in packets)


def _mchunk(text="", reasoning=None, cid=None, ns=""):
    ak = {"reasoning_content": reasoning} if reasoning else {}
    meta = {"langgraph_checkpoint_ns": ns} if ns else {}
    return ("messages", (AIMessageChunk(id=cid, content=text, additional_kwargs=ak), meta))


class _TwoStageFlowAgent(_FakeFlowAgent):
    """Stage 1 answers text-only (no tool). Stage 2 emits reasoning + answer
    BEFORE any tool call, split across chunks with DIFFERENT ids (what real
    langchain-ollama does) — the shape the old first_llm_call_id guard
    silently dropped for every stage past the first.

    Stage 2 (``node-stage-analysis``) is the ChatOutput-fed final stage, so
    its text is the answer bubble; stage 1's text folds into the timeline.
    """

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"node-stage-analysis"}

    async def astream(self, *args, **kwargs):
        yield ("debug", {"type": "task", "payload": {"id": "s1", "name": "node-stage-research"}})
        yield _mchunk("research briefing done", cid="s1-c1", ns="s1:aaa|model:x")
        yield (
            "debug",
            {"type": "task_result", "payload": {"id": "s1", "name": "node-stage-research"}},
        )
        yield ("debug", {"type": "task", "payload": {"id": "s2", "name": "node-stage-analysis"}})
        yield _mchunk(reasoning="analysis is thinking ", cid="s2-c1", ns="s2:bbb|model:y")
        yield _mchunk(reasoning="hard about numbers", cid="s2-c2", ns="s2:bbb|model:z")
        yield _mchunk("analysis ", cid="s2-c3", ns="s2:bbb|model:z")
        yield _mchunk("result", cid="s2-c4", ns="s2:bbb|model:w")
        yield (
            "debug",
            {"type": "task_result", "payload": {"id": "s2", "name": "node-stage-analysis"}},
        )


@pytest.mark.asyncio
async def test_second_stage_reasoning_streams_even_without_a_tool_call(monkeypatch):
    """Regression for "no thinking until the first tool call": a FlowAgent's
    non-first stage streams its reasoning + answer live even though its
    chunks carry several distinct ids and it never calls a tool."""
    packets = await _run(monkeypatch, _TwoStageFlowAgent())

    reasoning = "".join(
        p.get("reasoning", "") for p in packets if p.get("type") == "reasoning_delta"
    )
    assert "analysis is thinking hard about numbers" in reasoning
    # Stage 2 is the final stage -> its answer streams as tokens.
    tokens = "".join(p.get("content", "") for p in packets if p.get("type") == "token")
    assert "analysis" in tokens and "result" in tokens
    # Stage 1 is NOT final -> its text folds into the timeline, never the bubble.
    assert "research briefing done" not in tokens
    folded = "".join(
        p.get("content", "") for p in packets if p.get("type") == "flow_stage_output_delta"
    )
    assert "research briefing done" in folded
    # a fresh reasoning block opened for the second stage
    assert sum(1 for p in packets if p.get("type") == "reasoning_start") >= 1


class _FlowAgentWithToolsAndStages(_FakeFlowAgent):
    async def aget_state(self, *args, **kwargs):
        from langchain_core.messages import AIMessage, HumanMessage

        class _State:
            values = {
                "messages": [
                    HumanMessage(content="merhaba", id="h1"),
                    AIMessage(content="Final answer", id="ai-final-1"),
                ]
            }

        return _State()

    async def astream(self, *args, **kwargs):
        from langchain_core.messages import AIMessage, ToolMessage

        yield ("debug", {"type": "task", "payload": {"id": "t1", "name": "node-stage-research"}})
        yield (
            "updates",
            {
                "node-stage-research": {
                    "messages": [
                        AIMessage(
                            id="call-1",
                            content="",
                            tool_calls=[
                                {"name": "web_search", "args": {"query": "test"}, "id": "tc-1"}
                            ],
                        )
                    ]
                }
            },
        )
        yield (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            id="tool-1",
                            name="web_search",
                            content="search result",
                            tool_call_id="tc-1",
                        )
                    ]
                }
            },
        )
        yield (
            "debug",
            {"type": "task_result", "payload": {"id": "t1", "name": "node-stage-research"}},
        )
        yield ("debug", {"type": "task", "payload": {"id": "t2", "name": "node-stage-analysis"}})
        yield (
            "updates",
            {
                "node-stage-analysis": {
                    "messages": [
                        AIMessage(
                            id="call-2",
                            content="",
                            tool_calls=[
                                {
                                    "name": "execute_python_code",
                                    "args": {"code": "print(1)"},
                                    "id": "tc-2",
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
                "tools": {
                    "messages": [
                        ToolMessage(
                            id="tool-2",
                            name="execute_python_code",
                            content="1",
                            tool_call_id="tc-2",
                        )
                    ]
                }
            },
        )
        yield (
            "updates",
            {
                "node-stage-analysis": {
                    "messages": [AIMessage(id="ai-final-1", content="Final answer")]
                }
            },
        )
        yield (
            "debug",
            {"type": "task_result", "payload": {"id": "t2", "name": "node-stage-analysis"}},
        )


@pytest.mark.asyncio
async def test_flow_stage_timeline_persists_tool_events_with_timestamps(monkeypatch):
    import service.StoreService as StoreService
    from service.ChatHistoryReconstruction import _stage_timeline_packets

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {"persona_id": 3}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates, update_timestamp))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    await _run_with_thread(monkeypatch, _FlowAgentWithToolsAndStages())

    assert len(writes) == 1
    thread_id, updates, update_timestamp = writes[0]
    timelines = updates["metadata"]["flow_stage_timelines"]
    assert "ai-final-1" in timelines
    events = timelines["ai-final-1"]
    event_summary = [(e.get("stage_name") or e.get("tool_name"), e["event"]) for e in events]
    assert event_summary == [
        ("node-stage-research", "start"),
        ("web_search", "tool_start"),
        ("web_search", "tool_end"),
        ("node-stage-research", "end"),
        ("node-stage-analysis", "start"),
        ("execute_python_code", "tool_start"),
        ("execute_python_code", "tool_end"),
        ("node-stage-analysis", "end"),
    ]
    assert all(isinstance(e["timestamp"], int) for e in events)

    # Every persisted tool event records the stage that was running when it
    # fired, so reconstruction can attribute it without guesswork.
    tool_events = [e for e in events if e["event"] in ("tool_start", "tool_end")]
    assert [e["stage_node_id"] for e in tool_events] == [
        "node-stage-research",
        "node-stage-research",
        "node-stage-analysis",
        "node-stage-analysis",
    ]

    # Verify reconstruction replayed packets maintain chronological order and timestamps
    replayed = _stage_timeline_packets(events)
    assert len(replayed) == 8
    assert replayed[0]["obj"]["type"] == "graph_stage_start"
    assert replayed[1]["obj"]["type"] == "custom_tool_start"
    assert replayed[2]["obj"]["type"] == "custom_tool_delta"
    assert replayed[3]["obj"]["type"] == "graph_stage_end"
    assert replayed[4]["obj"]["type"] == "graph_stage_start"
    assert replayed[5]["obj"]["type"] == "custom_tool_start"
    assert replayed[6]["obj"]["type"] == "custom_tool_delta"
    assert replayed[7]["obj"]["type"] == "graph_stage_end"
    # ...and the replayed tool packets carry that node id through.
    assert replayed[1]["obj"]["stage_node_id"] == "node-stage-research"
    assert replayed[5]["obj"]["stage_node_id"] == "node-stage-analysis"


# ---------------------------------------------------------------------------
# Per-stage flow timeline (flow_stage_* packets): intermediate stages fold
# into the timeline, only the ChatOutput-fed stage streams the answer.
# ---------------------------------------------------------------------------


class _ThreeStageWithLoopFlowAgent(_FakeFlowAgent):
    """research -> (analysis x3 loop) -> answer. `answer` is the only final
    stage. `analysis` runs three iterations; `research` and every analysis
    pass fold into the timeline."""

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"answer"}

    async def astream(self, *args, **kwargs):
        yield ("debug", {"type": "task", "payload": {"id": "r", "name": "research"}})
        yield _mchunk("RESEARCH_TEXT", cid="r1", ns="r:aa|model:x")
        yield ("debug", {"type": "task_result", "payload": {"id": "r", "name": "research"}})
        for i in range(3):
            yield ("debug", {"type": "task", "payload": {"id": f"a{i}", "name": "analysis"}})
            yield _mchunk(f"ANALYSIS_{i} ", cid=f"a{i}c", ns=f"a{i}:bb|model:y")
            yield (
                "debug",
                {"type": "task_result", "payload": {"id": f"a{i}", "name": "analysis"}},
            )
        yield ("debug", {"type": "task", "payload": {"id": "f", "name": "answer"}})
        yield _mchunk("FINAL_ANSWER", cid="f1", ns="f:cc|model:z")
        yield ("debug", {"type": "task_result", "payload": {"id": "f", "name": "answer"}})


@pytest.mark.asyncio
async def test_intermediate_stage_output_folds_final_stage_streams(monkeypatch):
    packets = await _run(monkeypatch, _ThreeStageWithLoopFlowAgent())

    tokens = "".join(p.get("content", "") for p in packets if p.get("type") == "token")
    folded = "".join(
        p.get("content", "") for p in packets if p.get("type") == "flow_stage_output_delta"
    )
    assert "FINAL_ANSWER" in tokens
    assert "RESEARCH_TEXT" not in tokens and "ANALYSIS_0" not in tokens
    assert "RESEARCH_TEXT" in folded
    assert "ANALYSIS_0" in folded and "ANALYSIS_1" in folded and "ANALYSIS_2" in folded


@pytest.mark.asyncio
async def test_loop_stage_iterations_numbered(monkeypatch):
    packets = await _run(monkeypatch, _ThreeStageWithLoopFlowAgent())

    starts = [p for p in packets if p["type"] == "flow_stage_start" and p["node_id"] == "analysis"]
    assert [p["iteration"] for p in starts] == [1, 2, 3]
    orders = [p["stage_order"] for p in packets if p["type"] == "flow_stage_start"]
    assert orders == sorted(orders) and len(orders) == len(set(orders))


@pytest.mark.asyncio
async def test_flow_stage_start_and_end_bracket_each_timeline_stage(monkeypatch):
    packets = await _run(monkeypatch, _ThreeStageWithLoopFlowAgent())

    started = [p["stage_key"] for p in packets if p["type"] == "flow_stage_start"]
    ended = [p["stage_key"] for p in packets if p["type"] == "flow_stage_end"]
    assert started == ended
    # research + 3 analysis + answer = 5 timeline stages
    assert len(started) == 5
    for p in packets:
        if p["type"] == "flow_stage_end":
            assert p["status"] == "done"
            assert isinstance(p["duration_ms"], int)


@pytest.mark.asyncio
async def test_graph_stage_packets_still_emitted_alongside_flow_stage(monkeypatch):
    packets = await _run(monkeypatch, _ThreeStageWithLoopFlowAgent())
    assert any(p["type"] == "graph_stage_start" for p in packets)
    assert any(p["type"] == "graph_stage_end" for p in packets)
    assert any(p["type"] == "flow_stage_start" for p in packets)


@pytest.mark.asyncio
async def test_non_flow_agent_emits_no_flow_stage_packets(monkeypatch):
    """The isinstance(agent, FlowAgent) gate: a classic agent's stream never
    contains a flow_stage_* packet."""
    packets = await _run(monkeypatch, _NonFlowAgent())
    assert not any(str(p.get("type", "")).startswith("flow_stage_") for p in packets)


# ---------------------------------------------------------------------------
# Structured flow_timelines blob persistence (Task 7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_timelines_blob_persisted_alongside_legacy(monkeypatch):
    import service.StoreService as StoreService

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates, update_timestamp))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    class _Agent(_ThreeStageWithLoopFlowAgent):
        async def aget_state(self, *args, **kwargs):
            from langchain_core.messages import AIMessage, HumanMessage

            class _State:
                values = {
                    "messages": [
                        HumanMessage(content="q", id="h1"),
                        AIMessage(content="FINAL_ANSWER", id="ai-final-1"),
                    ]
                }

            return _State()

    await _run_with_thread(monkeypatch, _Agent())

    assert len(writes) == 1
    _, updates, _ = writes[0]
    md = updates["metadata"]
    assert "flow_stage_timelines" in md  # legacy event log still written
    blob = md["flow_timelines"]["ai-final-1"]
    assert [s["is_final"] for s in blob["stages"]].count(True) == 1
    assert blob["final_stage_key"] == blob["stages"][-1]["stage_key"]
    # research + analysis x3 + answer
    assert [s["node_id"] for s in blob["stages"]] == [
        "research",
        "analysis",
        "analysis",
        "analysis",
        "answer",
    ]
    assert [s["iteration"] for s in blob["stages"]] == [1, 1, 2, 3, 1]
    assert blob["stages"][-1]["output_text"] == "FINAL_ANSWER"


@pytest.mark.asyncio
async def test_non_flow_agent_writes_no_flow_timelines_key(monkeypatch):
    import service.StoreService as StoreService

    writes: list[tuple] = []

    async def _fake_get_thread(_thread_id):
        return {"metadata": {}}

    async def _fake_update(thread_id, updates, update_timestamp=True):
        writes.append((thread_id, updates, update_timestamp))
        return {}

    monkeypatch.setattr(StoreService, "get_thread_from_store", _fake_get_thread)
    monkeypatch.setattr(StoreService, "update_thread_in_store", _fake_update)

    await _run_with_thread(monkeypatch, _NonFlowAgent())

    assert writes == []


class _StageWithReasoningAgent(_FakeFlowAgent):
    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"answer"}

    async def astream(self, *args, **kwargs):
        yield ("debug", {"type": "task", "payload": {"id": "r", "name": "research"}})
        yield _mchunk(reasoning="pondering the sources ", cid="r1", ns="r:a|model:x")
        yield _mchunk("research done", cid="r2", ns="r:a|model:x")
        yield ("debug", {"type": "task_result", "payload": {"id": "r", "name": "research"}})
        yield ("debug", {"type": "task", "payload": {"id": "f", "name": "answer"}})
        yield _mchunk("ANSWER", cid="f1", ns="f:c|model:z")
        yield ("debug", {"type": "task_result", "payload": {"id": "f", "name": "answer"}})


@pytest.mark.asyncio
async def test_reasoning_start_and_delta_share_the_stage_key(monkeypatch):
    packets = await _run(monkeypatch, _StageWithReasoningAgent())
    starts = [p for p in packets if p["type"] == "reasoning_start"]
    deltas = [p for p in packets if p["type"] == "reasoning_delta"]
    assert starts and deltas
    # the non-final "research" stage's reasoning opener + body both carry its key
    assert any(p.get("stage_key", "").startswith("research") for p in starts)
    assert any(p.get("stage_key", "").startswith("research") for p in deltas)


class _SubgraphLeakFlowAgent(_FakeFlowAgent):
    """A stage whose compiled subgraph leaks its own internal `model` node's
    debug task/task_result events (3-tuple, namespaced). Those must NOT be
    turned into stages / loop iterations."""

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"answer"}

    async def astream(self, *args, **kwargs):
        # top-level: the canvas ReAct node
        yield ("debug", {"type": "task", "payload": {"id": "r", "name": "research"}})
        # subgraph-internal model calls — namespaced 3-tuples
        yield (
            ("research:uuid",),
            "debug",
            {"type": "task", "payload": {"id": "m1", "name": "model"}},
        )
        yield _mchunk(reasoning="iter 1 thinking", cid="m1c", ns="research:uuid|model:x")
        yield (
            ("research:uuid",),
            "debug",
            {"type": "task_result", "payload": {"id": "m1", "name": "model"}},
        )
        yield (
            ("research:uuid",),
            "debug",
            {"type": "task", "payload": {"id": "m2", "name": "model"}},
        )
        yield _mchunk(reasoning="iter 2 thinking", cid="m2c", ns="research:uuid|model:y")
        yield (
            ("research:uuid",),
            "debug",
            {"type": "task_result", "payload": {"id": "m2", "name": "model"}},
        )
        yield ("debug", {"type": "task_result", "payload": {"id": "r", "name": "research"}})
        yield ("debug", {"type": "task", "payload": {"id": "f", "name": "answer"}})
        yield _mchunk("FINAL", cid="f1", ns="answer:uuid|model:z")
        yield ("debug", {"type": "task_result", "payload": {"id": "f", "name": "answer"}})


@pytest.mark.asyncio
async def test_subgraph_internal_nodes_do_not_become_stages(monkeypatch):
    packets = await _run(monkeypatch, _SubgraphLeakFlowAgent())
    starts = [p for p in packets if p["type"] == "flow_stage_start"]
    # only the top-level canvas nodes are stages — no "model" stage, no loop
    # iterations from the subgraph's repeated internal model calls.
    assert [p["node_id"] for p in starts] == ["research", "answer"]
    assert all("model" not in p["stage_key"] for p in starts)
    assert all(p["iteration"] == 1 for p in starts)
    # both subgraph iterations' reasoning still attaches to that one stage
    reasoning = "".join(p.get("reasoning", "") for p in packets if p["type"] == "reasoning_delta")
    assert "iter 1 thinking" in reasoning and "iter 2 thinking" in reasoning


class _UnclosedThinkThenNextStageFlowAgent(_FakeFlowAgent):
    """Stage 1 (non-final) streams an OPEN ``<think>`` whose ``</think>`` +
    visible answer only arrive folded into the stage's `updates` message
    (what langchain-ollama aggregation does). Stage 2 (non-final) then
    streams a normal visible markdown answer as `messages` chunks.

    Regression: the run's single ThinkingTagProcessor was left mid-`<think>`
    at the stage seam, so stage 2's visible output was consumed as
    `reasoning_delta` and never streamed as `flow_stage_output_delta` — it
    only reached the client as the one-shot `updates` fallback (one packet
    with the whole answer), i.e. "the output isn't streamed, it just appears".
    """

    def __init__(self) -> None:
        super().__init__()
        self._final_stage_node_ids = {"node-answer"}

    async def astream(self, *args, **kwargs):
        from langchain_core.messages import AIMessage

        yield ("debug", {"type": "task", "payload": {"id": "s1", "name": "node-research"}})
        yield _mchunk("<think>arastirma ", cid="s1c", ns="node-research:aa|model:x")
        yield _mchunk("suruyor", cid="s1c", ns="node-research:aa|model:x")
        # </think> + the real answer only show up in the aggregated message
        yield (
            "updates",
            {"node-research": {"messages": [AIMessage(id="s1m", content="ARASTIRMA BRIFINGI")]}},
        )
        yield ("debug", {"type": "task_result", "payload": {"id": "s1", "name": "node-research"}})

        yield ("debug", {"type": "task", "payload": {"id": "s2", "name": "node-analysis"}})
        _md = "## HESAPLAMA OZETI\n\n- ortalama = 96256 token\n\nSonuc hazir.\n"
        for _i in range(0, len(_md), 6):
            yield _mchunk(_md[_i : _i + 6], cid="s2c", ns="node-analysis:bb|model:y")
        yield ("updates", {"node-analysis": {"messages": [AIMessage(id="s2m", content=_md)]}})
        yield ("debug", {"type": "task_result", "payload": {"id": "s2", "name": "node-analysis"}})


@pytest.mark.asyncio
async def test_unclosed_think_in_prior_stage_does_not_swallow_next_stage_output(monkeypatch):
    packets = await _run(monkeypatch, _UnclosedThinkThenNextStageFlowAgent())

    analysis_deltas = [
        p
        for p in packets
        if p.get("type") == "flow_stage_output_delta"
        and str(p.get("stage_key", "")).startswith("node-analysis")
    ]
    folded = "".join(p["content"] for p in analysis_deltas)
    assert "HESAPLAMA OZETI" in folded and "Sonuc hazir." in folded
    # streamed incrementally, not dumped as one `updates`-fallback packet
    assert len(analysis_deltas) >= 4

    # stage 2's visible markdown must NOT have leaked into the thinking stream
    reasoning = "".join(
        p.get("reasoning", "") for p in packets if p.get("type") == "reasoning_delta"
    )
    assert "HESAPLAMA OZETI" not in reasoning


class _FakeReActDynamicAgent:
    def __init__(self) -> None:
        pass

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        from langchain_core.messages import AIMessage

        yield (
            "updates",
            {"model": {"messages": [AIMessage(id="m1", content="dusunuyorum")]}},
        )
        yield (
            "updates",
            {"tools": {"messages": [AIMessage(id="t1", content="sonuc")]}},
        )
        yield (
            "updates",
            {"model": {"messages": [AIMessage(id="m2", content="nihai yanit")]}},
        )


class _FakePipelineDynamicAgent:
    def __init__(self) -> None:
        pass

    async def aget_state(self, *args, **kwargs):
        class _State:
            tasks = []
            values = {}

        return _State()

    async def astream(self, *args, **kwargs):
        from langchain_core.messages import AIMessage

        yield (
            "updates",
            {"researcher": {"messages": [AIMessage(id="r1", content="arastirma tamam")]}},
        )


@pytest.mark.asyncio
async def test_dynamic_agent_infra_nodes_never_emit_custom_step_start(monkeypatch):
    from agents.dynamic_agent import DynamicAgent

    class FakeAgent(_FakeReActDynamicAgent, DynamicAgent):
        def __init__(self):
            super().__init__()

    packets = await _run(monkeypatch, FakeAgent())
    assert not any(p.get("type") == "custom_step_start" for p in packets)


@pytest.mark.asyncio
async def test_dynamic_agent_custom_stage_emits_custom_step_start(monkeypatch):
    from agents.dynamic_agent import DynamicAgent

    class FakeAgent(_FakePipelineDynamicAgent, DynamicAgent):
        def __init__(self):
            super().__init__()

    packets = await _run(monkeypatch, FakeAgent())
    step_starts = [p for p in packets if p.get("type") == "custom_step_start"]
    assert len(step_starts) == 1
    assert step_starts[0]["step_name"] == "researcher"
