"""Tests for the input-port value primitive (Phase 4.5).

Langflow passes a value into a component along an edge. We carry the same idea
by naming the *producer* of the edge wired to a handle and reading its scratch
slot at runtime — the rule ``_make_arrival_stamp`` already used, now shared by
Loop's Items port, If-Else's Text Input and Smart Router's Override Output.

The distinction that matters: ``None`` means "nothing is wired", which is what
lets a caller fall back to the handle's declared field. An edge carrying an
empty value is *not* the same thing.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import _handle_source_id, _resolve_port_value
from models.flows import FlowEdge


def _edges() -> list[FlowEdge]:
    return [
        FlowEdge(
            id="e1",
            source="search",
            sourceHandle="results",
            target="loop",
            targetHandle="items",
        ),
        FlowEdge(
            id="e2",
            source="body",
            sourceHandle="output",
            target="loop",
            targetHandle="input",
        ),
    ]


def test_handle_source_id_finds_the_edge_by_target_handle():
    edges = _edges()
    assert _handle_source_id("loop", "items", edges) == "search"
    assert _handle_source_id("loop", "input", edges) == "body"


def test_handle_source_id_is_none_when_nothing_is_wired():
    assert _handle_source_id("loop", "missing", _edges()) is None
    assert _handle_source_id("other", "items", _edges()) is None


def test_resolve_port_value_reads_the_producers_scratch_slot():
    state = {"messages": [HumanMessage(content="son mesaj")], "scratch": {"search": [1, 2]}}
    assert _resolve_port_value(state, "search") == [1, 2]


def test_resolve_port_value_falls_back_to_the_latest_message():
    """A producer that writes no scratch slot (an agent) still carries a value:
    whatever it just said."""
    state = {"messages": [HumanMessage(content="son mesaj")], "scratch": {}}
    assert _resolve_port_value(state, "agent") == "son mesaj"


def test_resolve_port_value_is_none_when_no_edge_is_wired():
    state = {"messages": [HumanMessage(content="son mesaj")], "scratch": {"a": 1}}
    assert _resolve_port_value(state, None) is None


def test_resolve_port_value_preserves_a_falsy_scratch_value():
    """An edge carrying 0 / "" / [] is wired; only ``None`` means unwired."""
    state = {"messages": [], "scratch": {"p": []}}
    assert _resolve_port_value(state, "p") == []
