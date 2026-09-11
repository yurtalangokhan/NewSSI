"""Tests for FlowGraphBuilder.build() — assembling a validated FlowSpec into
a real, runnable StateGraph.

Assumes the caller (FlowService.validate_flow, P1 Task 6) already validated
the spec — this class does not re-validate. Router condition evaluation uses
a small, deliberately safe subset (a named scratch-key truthiness check), not
`eval()` — the same security stance Task 11's Loop condition will reuse.

Spec: .tmp/flow-canvas-design.md section 4.5.
Brief: .tmp/flow-canvas-task-10-brief.md
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from agents.graphs.flow_builder import FlowGraphBuilder, evaluate_condition
from models.flows import FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _linear_flow_dict() -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "Be terse."}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 10.1 — linear compile + run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_compiles_linear_chat_flow():
    spec = FlowSpec.model_validate(_linear_flow_dict())
    graph = await FlowGraphBuilder().build(spec)

    assert isinstance(graph, CompiledStateGraph)
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    assert len(result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 10.2 — resources never become graph nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_wires_resource_edges_without_adding_graph_nodes():
    data = _linear_flow_dict()
    data["nodes"].append({"id": "model-1", "type": "LLMModel", "values": {"model": "fake"}})
    data["edges"].append(
        {
            "id": "e3",
            "source": "model-1",
            "sourceHandle": "model",
            "target": "agent-1",
            "targetHandle": "model",
        }
    )
    spec = FlowSpec.model_validate(data)

    graph = await FlowGraphBuilder().build(spec)

    node_ids = set(graph.get_graph().nodes)
    assert "model-1" not in node_ids


# ---------------------------------------------------------------------------
# 10.3 — Router conditional branching
# ---------------------------------------------------------------------------


def test_evaluate_condition_checks_scratch_key_truthiness():
    """A condition is a scratch key name; truthy value -> route taken. No eval()."""
    assert evaluate_condition("go_left", {"scratch": {"go_left": True}}) is True
    assert evaluate_condition("go_left", {"scratch": {"go_left": False}}) is False
    assert evaluate_condition("go_left", {"scratch": {}}) is False


def test_evaluate_condition_does_not_execute_arbitrary_code():
    """A condition string containing something eval-shaped is inert, not executed."""
    state = {"scratch": {"__import__('os').system('echo pwned')": True}}
    # Treated as a literal (nonexistent) key name, never executed.
    assert evaluate_condition("__import__('os').system('echo pwned')", state) is True
    assert evaluate_condition("something_else", state) is False


@pytest.mark.asyncio
async def test_build_router_creates_conditional_branches():
    data = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "router-1",
                "type": "Router",
                "values": {"routes": [{"condition": "go_left", "route": "left"}]},
            },
            {"id": "agent-left", "type": "ZeroShotAgent", "values": {"system_prompt": "left"}},
            {"id": "agent-right", "type": "ZeroShotAgent", "values": {"system_prompt": "right"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "router-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "router-1",
                "sourceHandle": "left",
                "target": "agent-left",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "router-1",
                "sourceHandle": "default",
                "target": "agent-right",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "agent-left",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e5",
                "source": "agent-right",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    graph = await FlowGraphBuilder().build(spec)

    left_result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"go_left": True}}
    )
    right_result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    assert len(left_result["messages"]) >= 2
    assert len(right_result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 10.4 — precondition: an invalid spec raises clearly, not silently
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_raises_for_flow_missing_chat_input():
    from core.exceptions import FlowBuildError

    spec = FlowSpec.model_validate({"nodes": [{"id": "out-1", "type": "ChatOutput"}], "edges": []})

    with pytest.raises(FlowBuildError):
        await FlowGraphBuilder().build(spec)


# ---------------------------------------------------------------------------
# Bugfix #2 (live API testing) — defense in depth for reachability.
#
# Validation now rejects flows whose only entry→exit path traverses a
# resource node, but build() must not silently compile such a spec into a
# dead-end graph either: a spec that reaches build() unvalidated (e.g. a
# stale playground draft) would otherwise produce a run that looks successful
# while the flow silently does nothing.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_raises_when_exit_only_reachable_via_resource_node():
    """ChatInput → LLMModel → ChatOutput: both edges are resource wiring, so
    the compiled graph has no path to the exit — raise, don't dead-end."""
    from core.exceptions import FlowBuildError

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "model-1", "type": "LLMModel", "values": {"model": "fake"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "model-1",
                    "targetHandle": "model",
                },
                {
                    "id": "e2",
                    "source": "model-1",
                    "sourceHandle": "model",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )

    with pytest.raises(FlowBuildError, match="reachable"):
        await FlowGraphBuilder().build(spec)


# ---------------------------------------------------------------------------
# 10.5 — checkpointer respected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_respects_checkpointer():
    spec = FlowSpec.model_validate(_linear_flow_dict())
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)

    config = {"configurable": {"thread_id": "t1"}}
    await graph.ainvoke({"messages": [HumanMessage(content="first")], "scratch": {}}, config=config)
    await graph.ainvoke(
        {"messages": [HumanMessage(content="second")], "scratch": {}}, config=config
    )

    state = await graph.aget_state(config)
    assert len(state.values["messages"]) >= 4  # two full turns accumulated


# ---------------------------------------------------------------------------
# 10.6 — reproduces Task 0's spike findings against the real builder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_streaming_reproduces_task_0_findings():
    spec = FlowSpec.model_validate(_linear_flow_dict())
    graph = await FlowGraphBuilder().build(spec)

    chunks = []
    namespaces = set()
    async for ns, chunk in graph.astream(
        {"messages": [HumanMessage(content="hi")], "scratch": {}},
        stream_mode="messages",
        subgraphs=True,
    ):
        namespaces.add(str(ns))
        msg = chunk[0] if isinstance(chunk, tuple) else chunk
        if getattr(msg, "content", None):
            chunks.append(msg.content)

    assert len(chunks) > 0  # token-level streaming survived real assembly


# ---------------------------------------------------------------------------
# 10.7 — static fan-out: one node's output wired to *multiple* downstream
# agents (not Router's either/or branching — both run, unconditionally).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_fans_out_one_nodes_output_to_multiple_agents():
    """agent-1's output feeds BOTH agent-a and agent-b (two edges sharing the
    same source+sourceHandle, different targets) — both must run, and Merge
    must see both contributions before Chat Output. The edge-adding loop in
    FlowGraphBuilder.build() iterates every edge unconditionally (no
    dedup-by-source), so LangGraph's native multi-add_edge fan-out applies
    with zero extra compiler logic. This is distinct from `Send`-based
    *dynamic* fan-out (deferred, spec §4.5) — the branch count here is fixed
    at compile time by how many edges exist.
    """
    data = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "split"}},
            {"id": "agent-a", "type": "ZeroShotAgent", "values": {"system_prompt": "branch a"}},
            {"id": "agent-b", "type": "ZeroShotAgent", "values": {"system_prompt": "branch b"}},
            {"id": "merge-1", "type": "Merge", "values": {"strategy": "concat"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "agent-a",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "agent-b",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "agent-a",
                "sourceHandle": "output",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e5",
                "source": "agent-b",
                "sourceHandle": "output",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e6",
                "source": "merge-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    graph = await FlowGraphBuilder().build(spec)

    edges = graph.get_graph().edges
    targets_of_agent_1 = {e.target for e in edges if e.source == "agent-1"}
    assert targets_of_agent_1 == {"agent-a", "agent-b"}  # both wired, not just one

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    # in + agent-1 + agent-a + agent-b + merge(noop, adds nothing) = 4 AI messages + 1 human
    assert len(result["messages"]) >= 4


# ---------------------------------------------------------------------------
# 10.8 — sequential chaining: three agents run strictly in order, each fed by
# the previous one's output (a fixed pipeline, no dynamic dispatch decision).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_chains_three_agents_strictly_in_sequence():
    """No special 'pipeline' node is needed for this — chaining agent output
    handles (Message) into the next agent's input handle (Message) is just
    ordinary edges; add_edge enforces the order. Confirms sequential
    multi-agent chaining works with zero extra compiler logic, same as
    fan-out (10.7) needed none."""
    data = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "stage 1"}},
            {"id": "agent-2", "type": "ZeroShotAgent", "values": {"system_prompt": "stage 2"}},
            {"id": "agent-3", "type": "ZeroShotAgent", "values": {"system_prompt": "stage 3"}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "agent-1",
                "sourceHandle": "output",
                "target": "agent-2",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "agent-2",
                "sourceHandle": "output",
                "target": "agent-3",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "agent-3",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }
    spec = FlowSpec.model_validate(data)

    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    # 1 human + 3 agent responses, strictly ordered by add_edge chaining
    assert len(result["messages"]) >= 4


# ---------------------------------------------------------------------------
# Router v2 — operator comparisons; v1 rows are migrated on read
# ---------------------------------------------------------------------------


def _router_flow(routes: list[dict]) -> dict:
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "router-1", "type": "Router", "values": {"routes": routes}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "router-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "router-1",
                "sourceHandle": "left",
                "target": "out-1",
                "targetHandle": "message",
            },
            {
                "id": "e3",
                "source": "router-1",
                "sourceHandle": "default",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_router_migrates_a_v1_row_on_read():
    """A stored v1 row ({condition, route}) still routes: migrate_spec rewrites
    it to an is_truthy comparison inside build()."""
    spec = FlowSpec.model_validate(_router_flow([{"condition": "go_left", "route": "left"}]))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"go_left": True}}
    )
    assert result["messages"]


@pytest.mark.asyncio
async def test_router_migrates_a_v1_label_row_on_read():
    """The ancient hand-authored 'label' key is normalised to 'route' by the
    v1->v2 migration."""
    spec = FlowSpec.model_validate(_router_flow([{"condition": "go_left", "label": "left"}]))
    graph = await FlowGraphBuilder().build(spec)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"go_left": True}}
    )
    assert result["messages"]


@pytest.mark.asyncio
async def test_router_branches_on_an_operator_comparison():
    """v2: source names a Set Variable, compared with match_text via operator."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {"id": "set-1", "type": "SetVariable", "values": {"name": "score", "value": "7"}},
                {
                    "id": "router-1",
                    "type": "Router",
                    "values": {
                        "routes": [
                            {
                                "source": "score",
                                "operator": "greater_than",
                                "match_text": "5",
                                "route": "left",
                            },
                        ]
                    },
                },
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "set-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "set-1",
                    "sourceHandle": "output",
                    "target": "router-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "router-1",
                    "sourceHandle": "left",
                    "target": "out-1",
                    "targetHandle": "message",
                },
                {
                    "id": "e4",
                    "source": "router-1",
                    "sourceHandle": "default",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    # 7 > 5 -> "left" branch; the human message reaches ChatOutput unchanged
    assert result["messages"][-1].content == "hi"


@pytest.mark.asyncio
async def test_router_source_defaults_to_the_latest_message():
    """Blank source -> the latest message's text is the left operand."""
    spec = FlowSpec.model_validate(
        _router_flow([{"source": "", "operator": "contains", "match_text": "yes", "route": "left"}])
    )
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke({"messages": [HumanMessage(content="yes please")], "scratch": {}})
    assert result["messages"][-1].content == "yes please"


@pytest.mark.asyncio
async def test_prompt_template_can_feed_an_agent():
    """1.7 — Prompt Template's output is a Message now, so
    ChatInput -> PromptTemplate -> agent -> ChatOutput is type-valid and
    compiles (it was a FLOW_TYPE_MISMATCH dead end before)."""
    from domain.flows.validator import FLOW_TYPE_MISMATCH, validate

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "tpl-1",
                    "type": "PromptTemplate",
                    "values": {"template": "answer as a pirate"},
                },
                {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "tpl-1",
                    "targetHandle": "variables",
                },
                {
                    "id": "e2",
                    "source": "tpl-1",
                    "sourceHandle": "text",
                    "target": "agent-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "agent-1",
                    "sourceHandle": "output",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )

    assert not [i for i in validate(spec).errors if i.code == FLOW_TYPE_MISMATCH]

    graph = await FlowGraphBuilder().build(spec)
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    # the rendered prompt reached the stream, then the agent replied
    assert any(m.content == "answer as a pirate" for m in result["messages"])
    assert len(result["messages"]) >= 3
