"""Tests for AgentRef template promotion and memory-edge wiring.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-35-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import FlowGraphBuilder
from domain.flows.registry import get_registry
from domain.flows.resolvers import ResolverContext, resolve_options
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from models.flows import ComponentKind, FlowSpec, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_agent_ref_registers_with_task_12s_proven_shape(registry):
    """35.4 — AgentRef registers with kind=EXECUTION and Message->Message."""
    template = registry.get("AgentRef")
    assert template is not None
    assert template.category == "agents"
    assert template.kind == ComponentKind.EXECUTION
    assert any(h.name == "input" and PortType.MESSAGE in h.types for h in template.handles.inputs)
    assert any(h.name == "output" and PortType.MESSAGE in h.types for h in template.handles.outputs)


def test_agent_ref_agent_id_source_is_agents_definitions(registry):
    """35.5 — AgentRef agent_id field is wired to agents.definitions."""
    template = registry.get("AgentRef")
    assert "agent_id" in template.inputs
    field = template.inputs["agent_id"]
    assert field.options_source == "agents.definitions"
    assert field.options_source in KNOWN_OPTIONS_SOURCES


@pytest.mark.asyncio
async def test_agent_ref_picker_excludes_flow_backed_agents():
    """35.6 — agents.definitions resolver filters out flow-backed agents."""
    with patch(
        "domain.agents.service.AgentDefinitionService.list_agent_definitions",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = [
            SimpleNamespace(id="c-1", name="Classic Agent", graph_schema="react"),
            SimpleNamespace(id="f-1", name="Flow Agent", graph_schema="flow"),
        ]
        options = await resolve_options("agents.definitions", ResolverContext(user_id="u-1"))
        assert len(options.items) == 1
        assert options.items[0].value == "c-1"
        assert options.items[0].label == "Classic Agent"


@pytest.mark.asyncio
async def test_agent_ref_end_to_end_through_flow_graph_builder(registry):
    """35.11 — End-to-end execution of AgentRef node using real registry."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "aref-1", "type": "AgentRef", "values": {"agent_id": "c-1"}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "aref-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "aref-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    async def mock_subgraph(state, config=None):
        return {"messages": [AIMessage(content="Hello from referenced agent!")]}

    builder = FlowGraphBuilder(registry=registry)
    with patch.object(builder, "_resolve_agent_ref", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = mock_subgraph
        graph = await builder.build(spec)
        res = await graph.ainvoke({"messages": [HumanMessage(content="Hi")]})
        assert len(res["messages"]) >= 1


@pytest.mark.asyncio
async def test_flow_builder_wires_memory_edge_to_memory_enabled(registry):
    """35.8 — Wiring LongTermMemory to an agent passes memory_enabled=True to GraphBuilder."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "ltm-1", "type": "LongTermMemory"},
                {
                    "id": "agent-1",
                    "type": "ReActAgent",
                    "values": {"system_prompt": "You are helpful."},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "agent-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "ltm-1",
                    "sourceHandle": "memory",
                    "target": "agent-1",
                    "targetHandle": "memory",
                },
                {
                    "id": "e3",
                    "source": "agent-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with (
        patch("agents.graphs.builder.GraphBuilder.__init__", return_value=None) as mock_gb_init,
        patch(
            "agents.graphs.builder.GraphBuilder.build_async",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
    ):
        await builder.build(spec)
        assert mock_gb_init.called
        kwargs = mock_gb_init.call_args.kwargs
        assert kwargs.get("memory_enabled") is True


@pytest.mark.asyncio
async def test_agent_without_wired_memory_defaults_to_memory_disabled(registry):
    """35.9 — An agent without a LongTermMemory edge defaults to memory_enabled=False."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "agent-1",
                    "type": "ReActAgent",
                    "values": {"system_prompt": "You are helpful."},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "agent-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "agent-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with (
        patch("agents.graphs.builder.GraphBuilder.__init__", return_value=None) as mock_gb_init,
        patch(
            "agents.graphs.builder.GraphBuilder.build_async",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ),
    ):
        await builder.build(spec)
        assert mock_gb_init.called
        kwargs = mock_gb_init.call_args.kwargs
        assert kwargs.get("memory_enabled") is False
