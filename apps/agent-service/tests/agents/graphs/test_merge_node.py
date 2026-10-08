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
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.graphs.flow import FlowGraphBuilder
from schemas.flows import FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _two_branch_merge(strategy: str) -> dict:
    """ChatInput -> PromptTemplate(fast)  -> Merge -> ChatOutput
                 -> PromptTemplate(a) -> PromptTemplate(b) -> Merge
    The top branch reaches Merge one super-step sooner than the bottom one.

    PromptTemplate, not TextInput: TextInput's template declares no input
    handle at all (it is a literal-text *source*, B15) — wiring an edge into
    one is a shape the canvas can never actually produce, and the compiler's
    B15 fix then also gives it a START edge, so the node fires twice with a
    naive "input" edge like this one. PromptTemplate genuinely has an input
    handle ("variables"), matching how a first/last Merge's branches are
    really authored (see F13: SetVariable -> RunFlow -> RunFlow -> Merge).
    """
    return {
        "nodes": [
            {"id": "in-1", "type": "ChatInput"},
            {"id": "fast", "type": "PromptTemplate", "values": {"template": "FAST"}},
            {"id": "slow-a", "type": "PromptTemplate", "values": {"template": "SLOW-A"}},
            {"id": "slow-b", "type": "PromptTemplate", "values": {"template": "SLOW-B"}},
            {"id": "merge-1", "type": "Merge", "values": {"strategy": strategy}},
            {"id": "out-1", "type": "ChatOutput"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "fast",
                "targetHandle": "variables",
            },
            {
                "id": "e2",
                "source": "in-1",
                "sourceHandle": "message",
                "target": "slow-a",
                "targetHandle": "variables",
            },
            {
                "id": "e3",
                "source": "slow-a",
                "sourceHandle": "text",
                "target": "slow-b",
                "targetHandle": "variables",
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
async def test_builder_records_arrival_stamps_as_synthetic():
    """The compiler reports the stamp nodes it inserts so stage reporting
    can hide them without pattern-matching the naming scheme."""
    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_two_branch_merge("last")))
    assert builder.synthetic_node_ids == {
        "__arrival__merge-1__fast",
        "__arrival__merge-1__slow-b",
    }


@pytest.mark.asyncio
async def test_concat_adds_no_synthetic_nodes():
    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_two_branch_merge("concat")))
    assert builder.synthetic_node_ids == set()


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


@pytest.mark.asyncio
async def test_last_puts_the_chosen_branch_last():
    """`last` makes the latest branch's value the final message. B19: the
    losing branch's message never enters the transcript at all — every
    producer feeding only this Merge had its own message suppressed at
    compile time — so the only message the run adds is Merge's own."""
    spec = FlowSpec.model_validate(_two_branch_merge("last"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    contents = [m.content for m in result["messages"]]
    assert contents[-1] == "SLOW-B"
    assert contents == ["go", "SLOW-B"]  # no leftover FAST / SLOW-A bubble


@pytest.mark.asyncio
async def test_first_puts_the_chosen_branch_last():
    spec = FlowSpec.model_validate(_two_branch_merge("first"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    contents = [m.content for m in result["messages"]]
    assert contents[-1] == "FAST"
    assert contents == ["go", "FAST"]  # no leftover SLOW-A / SLOW-B bubble


@pytest.mark.asyncio
async def test_the_chosen_message_is_an_ai_message_not_a_human_one():
    """A HumanMessage here reads as the flow's answer being spoken by the
    user again. Live SSE streaming is type-agnostic (any message that isn't
    the user's own echoed input still renders), so this was invisible on
    the live turn — but every persistence check keys off `type == "ai"` to
    decide "this is the assistant's reply"; with the wrong type nothing was
    ever saved as one, and a reload showed the question with no answer."""
    spec = FlowSpec.model_validate(_two_branch_merge("last"))
    graph = await FlowGraphBuilder().build(spec)

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")], "scratch": {}},
        config={"recursion_limit": 50},
    )
    assert isinstance(result["messages"][-1], AIMessage)


@pytest.mark.asyncio
async def test_builder_records_merge_only_producers_as_message_suppressed():
    """B19: every producer whose sole consumer is the first/last Merge is
    flagged so its message never reaches the transcript — fast (direct) and
    both links of the slower chain (slow-a -> slow-b -> merge)."""
    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_two_branch_merge("last")))
    assert builder.message_suppressed_node_ids == {"fast", "slow-a", "slow-b"}


@pytest.mark.asyncio
async def test_concat_suppresses_no_messages():
    """concat is unaffected — nothing is merge-only under a strategy that
    was never going to retract anything."""
    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(_two_branch_merge("concat")))
    assert builder.message_suppressed_node_ids == set()


@pytest.mark.asyncio
async def test_a_branch_also_feeding_something_else_keeps_its_message():
    """A producer with a second, non-Merge consumer must not lose its
    message — some other branch may still need to read it."""
    spec = FlowSpec.model_validate(_two_branch_merge("last"))
    spec_dict = spec.model_dump(by_alias=True)
    # fast now also feeds a second ChatOutput directly — no longer merge-only
    spec_dict["nodes"].append({"id": "out-2", "type": "ChatOutput"})
    spec_dict["edges"].append(
        {
            "id": "e-extra",
            "source": "fast",
            "sourceHandle": "text",
            "target": "out-2",
            "targetHandle": "message",
        }
    )
    builder = FlowGraphBuilder()
    await builder.build(FlowSpec.model_validate(spec_dict))
    assert "fast" not in builder.message_suppressed_node_ids
    assert {"slow-a", "slow-b"} <= builder.message_suppressed_node_ids


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
