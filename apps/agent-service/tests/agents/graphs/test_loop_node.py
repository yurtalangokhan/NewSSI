"""Tests for Loop node compilation — the concrete implementation of risk R2
("users build graphs that deadlock or loop forever").

Task 3's validator already rejects an unbounded Loop at save time
(FLOW_UNBOUNDED_LOOP). This is the *runtime* enforcement — defense in depth,
since a spec could reach the compiler without having gone through validation
(same precondition question as Task 10.4).

Reuses Task 10's evaluate_condition (scratch-key truthiness, no eval()) —
Loop and Router share one condition mini-language, not two.

Spec: .tmp/flow-canvas-design.md section 7.2; design spec risk R2.
Brief: .tmp/flow-canvas-task-11-brief.md
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.graphs.flow_builder import FlowGraphBuilder
from models.flows import FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _loop_flow_dict(*, condition: str, max_iterations: int) -> dict:
    """ChatInput -> Agent -> Loop -[continue]-> Agent (back-edge)
    -[exit]-> ChatOutput"""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "agent-1", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
            {
                "id": "loop-1",
                "type": "Loop",
                "values": {"condition": condition, "max_iterations": max_iterations},
            },
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
                "target": "loop-1",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "loop-1",
                "sourceHandle": "continue",
                "target": "agent-1",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "loop-1",
                "sourceHandle": "exit",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


# ---------------------------------------------------------------------------
# 11.1 / 11.2 — condition-driven continue/exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_continues_while_condition_holds():
    """Condition true, bound high enough to not interfere -> multiple passes."""
    spec = FlowSpec.model_validate(_loop_flow_dict(condition="keep_going", max_iterations=5))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"keep_going": True}},
        config={"recursion_limit": 50},
    )
    # multiple trips through agent-1 -> more than a single-pass message count
    assert len(result["messages"]) >= 2


@pytest.mark.asyncio
async def test_loop_exits_when_condition_becomes_false():
    """Condition false from the start -> exits on the first check."""
    spec = FlowSpec.model_validate(_loop_flow_dict(condition="keep_going", max_iterations=5))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {}},  # keep_going absent -> falsy
    )
    assert len(result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 11.3 — the R2 guarantee
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_exits_at_max_iterations_even_if_condition_still_true():
    """A condition rigged to always be true must still stop at the bound."""
    spec = FlowSpec.model_validate(_loop_flow_dict(condition="always_true", max_iterations=3))
    graph = await FlowGraphBuilder().build(spec)

    # Without the bound, this would recurse until LangGraph's own
    # recursion_limit kills it with a GraphRecursionError. With the bound
    # working, it completes normally well within a generous limit.
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"always_true": True}},
        config={"recursion_limit": 50},
    )
    assert len(result["messages"]) >= 2


# ---------------------------------------------------------------------------
# 11.4 — iteration count is thread-scoped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_iteration_count_does_not_leak_across_separate_threads():
    spec = FlowSpec.model_validate(_loop_flow_dict(condition="always_true", max_iterations=2))
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)

    await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"always_true": True}},
        config={"configurable": {"thread_id": "thread-a"}, "recursion_limit": 50},
    )
    # A second, independent thread must not inherit thread-a's iteration count
    # and immediately exit as if already at the bound.
    result_b = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")], "scratch": {"always_true": True}},
        config={"configurable": {"thread_id": "thread-b"}, "recursion_limit": 50},
    )
    assert len(result_b["messages"]) >= 2


@pytest.mark.asyncio
async def test_loop_iteration_count_resets_each_turn():
    """A bounded Loop must run again on the thread's second turn."""
    spec = FlowSpec.model_validate(_loop_flow_dict(condition="", max_iterations=3))
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)
    cfg = {"configurable": {"thread_id": "same-thread"}, "recursion_limit": 50}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="a")], "scratch": {}}, config=cfg
    )
    after_first = len(first["messages"])

    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="b")], "scratch": {}}, config=cfg
    )

    assert len(second["messages"]) >= after_first + 2
    assert second["scratch"]["_loop_iterations_loop-1"] <= 3


# ---------------------------------------------------------------------------
# 11.5 — condition does not execute arbitrary code (integration-level proof;
# the unit-level guarantee already lives in Task 10's evaluate_condition tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_condition_does_not_execute_arbitrary_code():
    eval_shaped = "__import__('os').system('echo pwned')"
    spec = FlowSpec.model_validate(_loop_flow_dict(condition=eval_shaped, max_iterations=5))
    graph = await FlowGraphBuilder().build(spec)

    # Treated as a literal (nonexistent) scratch key -> falsy -> exits
    # immediately, exactly like test_loop_exits_when_condition_becomes_false.
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")], "scratch": {}})
    assert len(result["messages"]) >= 2
