"""Tests for the Merge node's first / last strategies.

``add_messages`` accumulates every branch's contribution before Merge runs,
so "which branch arrived first" is not in the flat message list. The compiler
routes each edge into a first/last Merge through an arrival-stamp node that
records the branch's message on an ordered ``arrivals`` channel; Merge then
re-emits the first / last one so it becomes the latest message.

``concat`` is unchanged — a pure passthrough.
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


def _two_branch_merge(strategy: str) -> dict:
    """ChatInput -> TextInput(fast)  -> Merge -> ChatOutput
                 -> TextInput(a) -> TextInput(b) -> Merge
    The top branch reaches Merge one super-step sooner than the bottom one."""
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "fast", "type": "TextInput", "values": {"text": "FAST"}},
            {"id": "slow-a", "type": "TextInput", "values": {"text": "SLOW-A"}},
            {"id": "slow-b", "type": "TextInput", "values": {"text": "SLOW-B"}},
            {"id": "merge-1", "type": "Merge", "values": {"strategy": strategy}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "fast",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "slow-a",
                "targetHandle": "input",
            },
            {
                "id": "e3",
                "source": "slow-a",
                "sourceHandle": "text",
                "target": "slow-b",
                "targetHandle": "input",
            },
            {
                "id": "e4",
                "source": "fast",
                "sourceHandle": "text",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e5",
                "source": "slow-b",
                "sourceHandle": "text",
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


@pytest.mark.asyncio
async def test_first_forwards_the_earliest_branch():
    spec = FlowSpec.model_validate(_two_branch_merge("first"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "FAST"


@pytest.mark.asyncio
async def test_last_forwards_the_latest_branch():
    spec = FlowSpec.model_validate(_two_branch_merge("last"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert result["messages"][-1].content == "SLOW-B"


@pytest.mark.asyncio
async def test_concat_is_unchanged():
    """concat stays a pure passthrough: every branch's message survives, in
    add_messages order, with nothing re-emitted."""
    spec = FlowSpec.model_validate(_two_branch_merge("concat"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    contents = [m.content for m in result["messages"]]
    assert "FAST" in contents and "SLOW-B" in contents


def _per_turn_merge(strategy: str) -> dict:
    """A two-branch Merge whose branch values differ per turn.

    ``SetVariable`` with a blank value stores the turn's own message text, so
    each branch renders a value that is unique to the turn. That is what makes
    a stale ``arrivals`` entry from an earlier turn visible: with static
    ``TextInput`` branches every turn produces the same string, and a leak
    looks identical to a correct answer.

        ChatInput -> cap -> fast              -> Merge -> ChatOutput
                        -> slow-a -> slow-b   -> Merge
    """
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "cap", "type": "SetVariable", "values": {"name": "turn"}},
            {"id": "fast", "type": "PromptTemplate", "values": {"template": "FAST-{turn}"}},
            {"id": "slow-a", "type": "PromptTemplate", "values": {"template": "SLOWA-{turn}"}},
            {"id": "slow-b", "type": "PromptTemplate", "values": {"template": "SLOWB-{turn}"}},
            {"id": "merge-1", "type": "Merge", "values": {"strategy": strategy}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "cap",
                "targetHandle": "input",
            },
            {
                "id": "e2",
                "source": "cap",
                "sourceHandle": "output",
                "target": "fast",
                "targetHandle": "variables",
            },
            {
                "id": "e3",
                "source": "cap",
                "sourceHandle": "output",
                "target": "slow-a",
                "targetHandle": "variables",
            },
            {
                "id": "e4",
                "source": "slow-a",
                "sourceHandle": "text",
                "target": "slow-b",
                "targetHandle": "variables",
            },
            {
                "id": "e5",
                "source": "fast",
                "sourceHandle": "text",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e6",
                "source": "slow-b",
                "sourceHandle": "text",
                "target": "merge-1",
                "targetHandle": "input",
            },
            {
                "id": "e7",
                "source": "merge-1",
                "sourceHandle": "output",
                "target": "out-1",
                "targetHandle": "message",
            },
        ],
    }


@pytest.mark.asyncio
async def test_first_does_not_leak_the_previous_turns_branch():
    """On a thread's second turn, `first` must name *this* turn's earliest
    branch — not the one recorded on turn one."""
    spec = FlowSpec.model_validate(_per_turn_merge("first"))
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)
    cfg = {"configurable": {"thread_id": "same-thread"}, "recursion_limit": 50}

    await graph.ainvoke({"messages": [HumanMessage(content="a")], "scratch": {}}, config=cfg)
    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="b")], "scratch": {}}, config=cfg
    )

    assert second["messages"][-1].content == "FAST-b"
