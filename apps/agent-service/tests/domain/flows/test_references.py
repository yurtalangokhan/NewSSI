"""Tests for the flow reference extractor.

The reference graph is a *different* graph from a flow's own node graph: its
vertices are agent definitions and its edges are RunFlow targets. Cycle
detection walks this one; ``FLOW_ILLEGAL_CYCLE`` walks the other.
"""

from __future__ import annotations

from domain.flows.references import flow_references
from models.flows import FlowSpec


def _spec(nodes: list[dict]) -> FlowSpec:
    return FlowSpec.model_validate({"nodes": nodes, "edges": []})


def test_collects_every_run_flow_target():
    spec = _spec(
        [
            {"id": "rf-1", "type": "RunFlow", "values": {"flow_id": "aaa"}},
            {"id": "rf-2", "type": "RunFlow", "values": {"flow_id": "bbb"}},
            {"id": "in-1", "type": "ChatInput"},
        ]
    )
    assert flow_references(spec) == {"aaa", "bbb"}


def test_the_same_target_twice_is_one_reference():
    spec = _spec(
        [
            {"id": "rf-1", "type": "RunFlow", "values": {"flow_id": "aaa"}},
            {"id": "rf-2", "type": "RunFlow", "values": {"flow_id": "aaa"}},
        ]
    )
    assert flow_references(spec) == {"aaa"}


def test_a_blank_or_missing_target_is_not_a_reference():
    """An unconfigured node is FLOW_RUNFLOW_MISSING_TARGET, not an edge to the
    empty string — treating it as one would turn a clear error into a
    confusing cycle report."""
    spec = _spec(
        [
            {"id": "rf-1", "type": "RunFlow", "values": {"flow_id": ""}},
            {"id": "rf-2", "type": "RunFlow", "values": {}},
            {"id": "rf-3", "type": "RunFlow", "values": {"flow_id": "   "}},
        ]
    )
    assert flow_references(spec) == set()


def test_other_node_types_contribute_nothing():
    """AgentRef and Supervisor keep their own ban (scope decision 5.5); they
    are not reference-graph edges."""
    spec = _spec(
        [
            {"id": "ar-1", "type": "AgentRef", "values": {"agent_id": "ccc"}},
            {"id": "sv-1", "type": "Supervisor", "values": {"sub_agents": ["ddd"]}},
        ]
    )
    assert flow_references(spec) == set()


def test_is_total_for_a_hand_edited_spec():
    """A stored spec is untrusted input, not a crash."""
    spec = _spec(
        [
            {"id": "rf-1", "type": "RunFlow", "values": {"flow_id": 123}},
            {"id": "rf-2", "type": "RunFlow", "values": {"flow_id": None}},
        ]
    )
    assert flow_references(spec) == {"123"}
