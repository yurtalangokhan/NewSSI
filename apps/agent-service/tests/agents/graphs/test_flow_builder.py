"""Tests for FlowState and the resource/execution node partition.

This is the first piece of the P2 compiler: the shared state schema every
compiled flow uses, and the function that separates build-time-injected
resource nodes from graph nodes proper.

Spec: .tmp/flow-canvas-design.md sections 4.3, 4.5.
Brief: .tmp/flow-canvas-task-7-brief.md
"""

from __future__ import annotations

from typing import get_type_hints

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from agents.graphs.flow_builder import FlowState, partition_nodes
from core.exceptions import UnknownComponentError
from domain.flows.registry import ComponentRegistry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FlowNode,
    Handle,
    PortType,
)


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentTemplate(
            type="FakeResource",
            category="test",
            display_name="Fake Resource",
            kind=ComponentKind.RESOURCE,
            handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MODEL])]),
        )
    )
    registry.register(
        ComponentTemplate(
            type="FakeExecution",
            category="test",
            display_name="Fake Execution",
            kind=ComponentKind.EXECUTION,
            handles=ComponentHandles(outputs=[Handle(name="out", types=[PortType.MESSAGE])]),
        )
    )
    return registry


# ---------------------------------------------------------------------------
# FlowState
# ---------------------------------------------------------------------------


def _reducer_for(field_name: str):
    """Extract the Annotated reducer for a FlowState field.

    FlowState uses `from __future__ import annotations`, so raw
    `__annotations__` access yields unresolved ForwardRefs, not the actual
    `Annotated[...]` object. `get_type_hints(..., include_extras=True)`
    resolves them properly.
    """
    hints = get_type_hints(FlowState, include_extras=True)
    return hints[field_name].__metadata__[0]


def test_flow_state_accumulates_messages():
    """7.1 — messages use LangGraph's own add_messages reducer."""
    assert _reducer_for("messages") is add_messages

    first = add_messages([HumanMessage(content="hi")], [AIMessage(content="hello")])
    assert len(first) == 2


def test_flow_state_scratch_merges_across_updates():
    """7.2 — two updates to scratch with different keys both survive."""
    reducer = _reducer_for("scratch")

    merged = reducer({"a": 1}, {"b": 2})

    assert merged == {"a": 1, "b": 2}


def test_flow_state_scratch_last_write_wins_on_same_key():
    """7.3 — same key: second update wins. Deliberate, not a bug."""
    reducer = _reducer_for("scratch")

    merged = reducer({"a": 1}, {"a": 2})

    assert merged == {"a": 2}


# ---------------------------------------------------------------------------
# partition_nodes
# ---------------------------------------------------------------------------


def test_partition_separates_resources_from_executions():
    """7.4 — a resource-kind node and an execution-kind node land in the right list."""
    registry = _registry()
    spec_nodes = [
        FlowNode(id="r1", type="FakeResource"),
        FlowNode(id="e1", type="FakeExecution"),
    ]

    resources, executions = partition_nodes(spec_nodes, registry)

    assert [n.id for n in resources] == ["r1"]
    assert [n.id for n in executions] == ["e1"]


def test_partition_preserves_original_node_order():
    """7.5 — order within each list matches the original node order."""
    registry = _registry()
    spec_nodes = [
        FlowNode(id="e1", type="FakeExecution"),
        FlowNode(id="r1", type="FakeResource"),
        FlowNode(id="e2", type="FakeExecution"),
        FlowNode(id="r2", type="FakeResource"),
    ]

    resources, executions = partition_nodes(spec_nodes, registry)

    assert [n.id for n in resources] == ["r1", "r2"]
    assert [n.id for n in executions] == ["e1", "e2"]


def test_partition_raises_for_unknown_component_type():
    """7.6 — an unknown type at this stage is a programming error, not a
    silent skip; validation should already have caught it upstream."""
    registry = _registry()
    spec_nodes = [FlowNode(id="mystery-1", type="TotallyMadeUp")]

    with pytest.raises(UnknownComponentError):
        partition_nodes(spec_nodes, registry)


# ---------------------------------------------------------------------------
# tool_mode — a per-node mode the template must declare
# ---------------------------------------------------------------------------


def test_a_tool_mode_node_is_partitioned_as_a_resource():
    """A node used as a tool must not also become a graph node: the agent
    calls it, the flow does not run it."""
    from agents.graphs.flow_builder import partition_nodes
    from domain.flows.registry import get_registry

    nodes = [
        FlowNode(id="in-1", type="ChatInput"),
        FlowNode(id="ws-1", type="WebSearch", values={"tool_mode": True}),
        FlowNode(id="out-1", type="ChatOutput"),
    ]
    resources, executions = partition_nodes(nodes, get_registry())
    assert [n.id for n in resources] == ["ws-1"]
    assert [n.id for n in executions] == ["in-1", "out-1"]


def test_the_same_node_without_tool_mode_stays_an_execution_node():
    from agents.graphs.flow_builder import partition_nodes
    from domain.flows.registry import get_registry

    nodes = [FlowNode(id="ws-1", type="WebSearch", values={"tool_mode": False})]
    resources, executions = partition_nodes(nodes, get_registry())
    assert [n.id for n in executions] == ["ws-1"]
    assert resources == []


def test_a_template_that_declares_no_tool_mode_field_ignores_the_value():
    """Decision 6.2: the capability is declared by the template. A stray
    `tool_mode: true` on a control-flow node must change nothing."""
    from agents.graphs.flow_builder import partition_nodes
    from domain.flows.registry import get_registry

    nodes = [FlowNode(id="m-1", type="Merge", values={"tool_mode": True, "strategy": "concat"})]
    resources, executions = partition_nodes(nodes, get_registry())
    assert [n.id for n in executions] == ["m-1"]
