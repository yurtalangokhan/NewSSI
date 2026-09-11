"""Tests for Loop as a foreach over a collection (Langflow's LoopComponent).

Sequential: the graph re-enters the Loop node once per item. ``item`` carries
the current element to the body; the body loops back; ``done`` carries the
joined results once the list is exhausted.

The pre-Phase-3 counter loop is the separate ``While`` type
(test_loop_node.py still covers it, via the v1->While rename).
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import (
    FlowGraphBuilder,
    _make_foreach_node,
    _make_foreach_route_fn,
    _resolve_loop_items,
)
from models.flows import FlowNode, FlowSpec


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


def _node() -> FlowNode:
    return FlowNode(id="loop-1", type="Loop", values={"items_source": "xs"})


@pytest.mark.asyncio
async def test_first_entry_resolves_the_collection_and_emits_the_first_item():
    fn = _make_foreach_node(_node())
    result = await fn(
        {"messages": [HumanMessage(content="go")], "scratch": {"xs": ["a", "b", "c"]}}, None
    )
    assert result["scratch"]["_foreach_items_loop-1"] == ["a", "b", "c"]
    assert result["scratch"]["_foreach_idx_loop-1"] == 0
    assert result["messages"][0].content == "a"


@pytest.mark.asyncio
async def test_reentry_collects_the_body_output_and_advances():
    fn = _make_foreach_node(_node())
    scratch = {
        "_foreach_items_loop-1": ["a", "b", "c"],
        "_foreach_idx_loop-1": 0,
        "_foreach_agg_loop-1": [],
    }
    result = await fn({"messages": [AIMessage(content="A")], "scratch": scratch}, None)
    assert result["scratch"]["_foreach_idx_loop-1"] == 1
    assert result["scratch"]["_foreach_agg_loop-1"] == ["A"]
    assert result["messages"][0].content == "b"


@pytest.mark.asyncio
async def test_after_the_last_item_it_emits_the_joined_results():
    fn = _make_foreach_node(_node())
    scratch = {
        "_foreach_items_loop-1": ["a", "b"],
        "_foreach_idx_loop-1": 1,
        "_foreach_agg_loop-1": ["A"],
    }
    result = await fn({"messages": [AIMessage(content="B")], "scratch": scratch}, None)
    assert result["scratch"]["_foreach_idx_loop-1"] == 2
    assert result["scratch"]["loop-1"] == ["A", "B"]
    assert result["messages"][0].content == "A\nB"


@pytest.mark.asyncio
async def test_empty_collection_goes_straight_to_done():
    fn = _make_foreach_node(_node())
    result = await fn({"messages": [HumanMessage(content="go")], "scratch": {"xs": []}}, None)
    assert result["scratch"]["loop-1"] == []
    assert result["messages"][0].content == ""


@pytest.mark.asyncio
async def test_no_source_iterates_the_latest_message_lines():
    fn = _make_foreach_node(FlowNode(id="loop-1", type="Loop", values={"items_source": ""}))
    result = await fn(
        {"messages": [HumanMessage(content="one\n\ntwo\nthree")], "scratch": {}}, None
    )
    assert result["scratch"]["_foreach_items_loop-1"] == ["one", "two", "three"]


def test_route_fn_picks_item_then_done():
    from models.flows import FlowEdge

    route = _make_foreach_route_fn(
        _node(),
        [
            FlowEdge(
                id="e-item",
                source="loop-1",
                sourceHandle="item",
                target="body",
                targetHandle="input",
            ),
            FlowEdge(
                id="e-done",
                source="loop-1",
                sourceHandle="done",
                target="out",
                targetHandle="message",
            ),
        ],
    )
    assert (
        route({"scratch": {"_foreach_idx_loop-1": 0, "_foreach_items_loop-1": ["a", "b"]}})
        == "body"
    )
    assert (
        route({"scratch": {"_foreach_idx_loop-1": 2, "_foreach_items_loop-1": ["a", "b"]}}) == "out"
    )


@pytest.mark.asyncio
async def test_compiles_and_runs_the_body_once_per_line():
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "loop-1",
                    "type": "Loop",
                    "template_version": 2,
                    "values": {"items_source": ""},
                },
                {"id": "a", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "loop-1",
                    "sourceHandle": "item",
                    "target": "a",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "a",
                    "sourceHandle": "output",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e4",
                    "source": "loop-1",
                    "sourceHandle": "done",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    graph = await FlowGraphBuilder().build(spec)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="one\ntwo\nthree")], "scratch": {}},
        config={"recursion_limit": 200},
    )
    # three items collected under the node id
    assert len(result["scratch"]["loop-1"]) == 3


@pytest.mark.asyncio
async def test_iteration_state_resets_each_turn():
    from langgraph.checkpoint.memory import MemorySaver

    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "loop-1",
                    "type": "Loop",
                    "template_version": 2,
                    "values": {"items_source": ""},
                },
                {"id": "a", "type": "ZeroShotAgent", "values": {"system_prompt": "hi"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "loop-1",
                    "sourceHandle": "item",
                    "target": "a",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "a",
                    "sourceHandle": "output",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e4",
                    "source": "loop-1",
                    "sourceHandle": "done",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    saver = MemorySaver()
    graph = await FlowGraphBuilder(checkpointer=saver).build(spec)
    cfg = {"configurable": {"thread_id": "t"}, "recursion_limit": 200}

    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="a\nb")], "scratch": {}}, config=cfg
    )
    assert len(first["scratch"]["loop-1"]) == 2

    second = await graph.ainvoke(
        {"messages": [HumanMessage(content="x\ny\nz")], "scratch": {}}, config=cfg
    )
    # turn two starts fresh: three items, not carried over from turn one
    assert len(second["scratch"]["loop-1"]) == 3


# ---------------------------------------------------------------------------
# Langflow parity (Phase 4.5): the collection arrives on a port
#
# Langflow's Loop takes its collection through a HandleInput accepting
# DataFrame / Table / Data / Message. Before this, ours could realistically
# only iterate the lines of the latest message: the field named a Set Variable,
# and nothing but a hand-typed node id could name a real collection.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_items_port_carries_structured_rows():
    fn = _make_foreach_node(
        FlowNode(id="loop-1", type="Loop", values={"items_source": ""}),
        port_sources={"items": "search-1"},
    )
    rows = [{"content": "a"}, {"content": "b"}]
    result = await fn(
        {"messages": [HumanMessage(content="q")], "scratch": {"search-1": rows}}, None
    )
    assert result["scratch"]["_foreach_items_loop-1"] == rows


@pytest.mark.asyncio
async def test_items_port_beats_the_items_source_field():
    fn = _make_foreach_node(
        FlowNode(id="loop-1", type="Loop", values={"items_source": "xs"}),
        port_sources={"items": "search-1"},
    )
    result = await fn({"messages": [], "scratch": {"xs": ["field"], "search-1": ["port"]}}, None)
    assert result["scratch"]["_foreach_items_loop-1"] == ["port"]


def test_resolve_loop_items_widens_the_accepted_shapes():
    state = {"messages": [HumanMessage(content="bir\n\niki")], "scratch": {"v": [1, 2]}}
    assert _resolve_loop_items("v", state) == [1, 2]
    assert _resolve_loop_items("", state) == ["bir", "iki"]  # blank lines dropped
    assert _resolve_loop_items("", {"messages": [], "scratch": {}}) == []
    # A single non-list value is one item, not a crash.
    assert _resolve_loop_items("v", {"messages": [], "scratch": {"v": 7}}) == [7]
    # A named source that holds nothing iterates nothing — it does not silently
    # fall back to the message, which would run the body over the wrong data.
    assert _resolve_loop_items("missing", state) == []


@pytest.mark.asyncio
async def test_the_node_id_slot_carries_the_item_then_the_aggregate():
    """Langflow has two outputs: `item` is a Data, `done` a DataFrame. We have
    one scratch slot and two branches that are never live at once, so the slot
    means "current item" while iterating and "collected results" at the end.

    Before this the item went to `_foreach_item_<id>`, which no consumer could
    read: it starts with an underscore and contains a dash, so it is not a
    valid str.format placeholder. The structure was simply lost.
    """
    fn = _make_foreach_node(FlowNode(id="loop-1", type="Loop", values={"items_source": "xs"}))

    first = await fn({"messages": [], "scratch": {"xs": [{"n": 1}, {"n": 2}]}}, None)
    assert first["scratch"]["loop-1"] == {"n": 1}

    second = await fn(
        {"messages": [AIMessage(content="first result")], "scratch": {**first["scratch"]}}, None
    )
    assert second["scratch"]["loop-1"] == {"n": 2}

    done = await fn(
        {"messages": [AIMessage(content="second result")], "scratch": {**second["scratch"]}}, None
    )
    assert done["scratch"]["loop-1"] == ["first result", "second result"]


@pytest.mark.asyncio
async def test_aggregation_prefers_the_body_ends_structured_value():
    """Langflow aggregates the loop body's end-vertex *output*. Collecting the
    message text flattened whatever the body produced; reading the body end's
    scratch slot keeps it."""
    fn = _make_foreach_node(
        FlowNode(id="loop-1", type="Loop", values={"items_source": "xs"}),
        body_end_id="pt-1",
    )
    first = await fn({"messages": [], "scratch": {"xs": ["a", "b"]}}, None)
    second = await fn(
        {
            "messages": [AIMessage(content="flattened")],
            "scratch": {**first["scratch"], "pt-1": {"structured": 1}},
        },
        None,
    )
    assert second["scratch"]["_foreach_agg_loop-1"] == [{"structured": 1}]


@pytest.mark.asyncio
async def test_aggregation_falls_back_to_the_message_when_the_body_writes_none():
    """An agent-terminated body publishes no scratch slot; what it just said is
    still the value it produced."""
    fn = _make_foreach_node(
        FlowNode(id="loop-1", type="Loop", values={"items_source": "xs"}),
        body_end_id="agent-1",
    )
    first = await fn({"messages": [], "scratch": {"xs": ["a", "b"]}}, None)
    second = await fn(
        {"messages": [AIMessage(content="said this")], "scratch": {**first["scratch"]}}, None
    )
    assert second["scratch"]["_foreach_agg_loop-1"] == ["said this"]


@pytest.mark.asyncio
async def test_the_body_end_is_the_body_not_whatever_wires_in_first():
    """Two edges land on a Loop's `input`: Chat Input at the start of the turn,
    and the body's last node on every pass. Picking the first one found made
    the aggregate collect the wrong value — and Chat Input comes first in every
    normally-drawn flow, so this was the common case, not an edge case."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in-1", "type": "ChatInput"},
                {
                    "id": "loop-1",
                    "type": "Loop",
                    "template_version": 2,
                    "values": {"items_source": "xs"},
                },
                # A body whose scratch value and message differ, so the assertion
                # can tell which one the aggregate actually collected.
                {
                    "id": "body",
                    "type": "Operations",
                    "values": {
                        "operation": "Append or Update",
                        "append_update_data": {"govde": True},
                    },
                },
                {"id": "after", "type": "PromptTemplate", "values": {"template": "BITTI"}},
                {"id": "out-1", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in-1",
                    "sourceHandle": "message",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "loop-1",
                    "sourceHandle": "item",
                    "target": "body",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "body",
                    "sourceHandle": "data_output",
                    "target": "loop-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e4",
                    "source": "loop-1",
                    "sourceHandle": "done",
                    "target": "after",
                    "targetHandle": "variables",
                },
                {
                    "id": "e5",
                    "source": "after",
                    "sourceHandle": "text",
                    "target": "out-1",
                    "targetHandle": "message",
                },
            ],
        }
    )
    graph = await FlowGraphBuilder().build(spec)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="basla")], "scratch": {"xs": ["a", "b"]}}
    )
    # The body's own value, not the message it happened to render.
    assert result["scratch"]["loop-1"] == [{"govde": True}, {"govde": True}]


@pytest.mark.asyncio
async def test_a_table_wired_into_items_iterates_its_rows():
    """Langflow's Loop expands a DataFrame to its rows. Split Text produces a
    table, so without this the whole table becomes a single item."""
    import pandas as pd

    fn = _make_foreach_node(
        FlowNode(id="loop-1", type="Loop", values={"items_source": ""}),
        port_sources={"items": "bol"},
    )
    frame = pd.DataFrame({"text": ["bir", "iki", "uc"]})
    result = await fn({"messages": [], "scratch": {"bol": frame}}, None)
    assert result["scratch"]["_foreach_items_loop-1"] == [
        {"text": "bir"},
        {"text": "iki"},
        {"text": "uc"},
    ]
