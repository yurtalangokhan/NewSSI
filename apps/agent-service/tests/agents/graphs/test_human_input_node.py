"""Tests for Human Input — pause the flow, ask a person, branch on their answer.

A faithful port of Langflow's Human Input on the platform's existing
interrupt/resume pipeline. No timeout: the run waits in the thread.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.graphs.flow_builder import (
    FlowGraphBuilder,
    _human_input_result_key,
    _make_human_input_node,
    _match_decision,
)
from core.exceptions import FlowBuildError
from models.flows import FlowNode, FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _hitl_flow(*, enable_unmatched=False, wire_unmatched=False) -> dict:
    edges = [
        {
            "id": "e1",
            "source": "in-1",
            "sourceHandle": "message",
            "target": "hi-1",
            "targetHandle": "input",
        },
        {
            "id": "e2",
            "source": "hi-1",
            "sourceHandle": "approve",
            "target": "approved",
            "targetHandle": "message",
        },
        {
            "id": "e3",
            "source": "hi-1",
            "sourceHandle": "reject",
            "target": "rejected",
            "targetHandle": "message",
        },
    ]
    if wire_unmatched:
        edges.append(
            {
                "id": "e4",
                "source": "hi-1",
                "sourceHandle": "unmatched",
                "target": "rejected",
                "targetHandle": "message",
            }
        )
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {
                "id": "hi-1",
                "type": "HumanInput",
                "values": {
                    "prompt": "Ship it?",
                    "decisions": [{"label": "approve"}, {"label": "reject"}],
                    "enable_unmatched": enable_unmatched,
                },
            },
            {"id": "approved", "type": "ChatOutput"},
            {"id": "rejected", "type": "ChatOutput"},
        ],
        "edges": edges,
    }


async def _build(spec_dict):
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(FlowSpec.model_validate(spec_dict))
    return graph


@pytest.mark.asyncio
async def test_first_pass_interrupts_with_the_prompt_and_action_list():
    graph = await _build(_hitl_flow())
    cfg = {"configurable": {"thread_id": "t1"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)

    state = await graph.aget_state(cfg)
    interrupts = [i for task in state.tasks for i in getattr(task, "interrupts", [])]
    assert interrupts, "the flow should be paused at the Human Input node"
    payload = interrupts[0].value
    assert payload["type"] == "human_input"
    assert payload["node_id"] == "hi-1"
    assert payload["prompt"] == "Ship it?"
    assert payload["decisions"] == ["approve", "reject"]


@pytest.mark.asyncio
async def test_resume_selects_the_matching_branch():
    graph = await _build(_hitl_flow())
    cfg = {"configurable": {"thread_id": "t2"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)
    result = await graph.ainvoke(Command(resume="approve"), config=cfg)

    assert result["scratch"][_human_input_result_key("hi-1")] == "approve"


@pytest.mark.asyncio
async def test_structured_resume_payload_is_accepted():
    graph = await _build(_hitl_flow())
    cfg = {"configurable": {"thread_id": "t3"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)
    result = await graph.ainvoke(Command(resume={"decision": "reject"}), config=cfg)

    assert result["scratch"][_human_input_result_key("hi-1")] == "reject"


@pytest.mark.asyncio
async def test_unmatched_resume_takes_the_unmatched_branch_when_enabled():
    graph = await _build(_hitl_flow(enable_unmatched=True, wire_unmatched=True))
    cfg = {"configurable": {"thread_id": "t4"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)
    result = await graph.ainvoke(Command(resume="maybe later"), config=cfg)

    assert result["scratch"][_human_input_result_key("hi-1")] == "__unmatched__"


@pytest.mark.asyncio
async def test_unmatched_resume_without_fallback_is_an_error():
    graph = await _build(_hitl_flow(enable_unmatched=False))
    cfg = {"configurable": {"thread_id": "t5"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)
    with pytest.raises(FlowBuildError):
        await graph.ainvoke(Command(resume="nonsense"), config=cfg)


@pytest.mark.asyncio
async def test_resume_does_not_reset_iteration_counters():
    """Phase 0's recorded assumption, now testable: ChatInput's per-turn
    counter reset runs only from START, and Command(resume=...) resumes from
    the interrupted node — so a While counter is preserved across a
    human-input pause inside its body."""
    spec = {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "while-1", "type": "While", "values": {"condition": "", "max_iterations": 3}},
            {
                "id": "hi-1",
                "type": "HumanInput",
                "values": {
                    "prompt": "continue?",
                    "decisions": [{"label": "go"}],
                },
            },
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "while-1",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "while-1",
                "sourceHandle": "continue",
                "target": "hi-1",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "hi-1",
                "sourceHandle": "go",
                "target": "while-1",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "while-1",
                "sourceHandle": "exit",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }
    graph = await _build(spec)
    cfg = {"configurable": {"thread_id": "t6"}, "recursion_limit": 60}

    await graph.ainvoke({"messages": [HumanMessage(content="go")], "scratch": {}}, config=cfg)
    # Each resume advances the While by one. If the counter were reset on
    # resume the loop would never end; three resumes reach the bound.
    await graph.ainvoke(Command(resume="go"), config=cfg)
    await graph.ainvoke(Command(resume="go"), config=cfg)
    result = await graph.ainvoke(Command(resume="go"), config=cfg)

    assert result["scratch"]["_loop_iterations_while-1"] == 3
    state = await graph.aget_state(cfg)
    assert not [i for task in state.tasks for i in getattr(task, "interrupts", [])]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("approve", "approve"),
        ("  Approve ", "approve"),
        ({"decision": "reject"}, "reject"),
        ({"decision": "REJECT"}, "reject"),
        ("nonsense", None),
        ({"decision": ""}, None),
        ("", None),
    ],
)
def test_match_decision_accepts_string_and_structured_answers(answer, expected):
    assert _match_decision(answer, ["approve", "reject"]) == expected


@pytest.mark.asyncio
async def test_unmatched_answer_takes_the_unmatched_branch_when_enabled():
    node = FlowNode(
        id="hi-1",
        type="HumanInput",
        template_version=2,
        values={"prompt": "?", "decisions": [{"label": "Onayla"}], "enable_unmatched": True},
    )
    fn = _make_human_input_node(node)
    with patch("agents.graphs.flow_builder.interrupt", return_value="bambaska"):
        result = await fn({"messages": [], "scratch": {}}, None)
    assert result["scratch"][_human_input_result_key("hi-1")] == "__unmatched__"


@pytest.mark.asyncio
async def test_unmatched_answer_without_the_branch_is_an_error():
    node = FlowNode(
        id="hi-1",
        type="HumanInput",
        template_version=2,
        values={"prompt": "?", "decisions": [{"label": "Onayla"}], "enable_unmatched": False},
    )
    fn = _make_human_input_node(node)
    with patch("agents.graphs.flow_builder.interrupt", return_value="bambaska"):
        with pytest.raises(FlowBuildError):
            await fn({"messages": [], "scratch": {}}, None)
