"""Tests for Supervisor multi-agent template and compiler handler.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-37-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import FlowGraphBuilder
from core.exceptions import FlowBuildError
from domain.flows.registry import get_registry
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, FieldType, FlowSpec, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_supervisor_template_registers(registry):
    """37.1 — Supervisor template registers in agents category with kind=EXECUTION."""
    template = registry.get("Supervisor")
    assert template is not None
    assert template.category == "agents"
    assert template.kind == ComponentKind.EXECUTION
    assert any(h.name == "input" and PortType.MESSAGE in h.types for h in template.handles.inputs)
    assert any(h.name == "output" and PortType.MESSAGE in h.types for h in template.handles.outputs)


def test_supervisor_sub_agents_field_is_multiselect_of_agent_definitions(registry):
    """37.2 — Supervisor sub_agents is MULTISELECT wired to agents.definitions."""
    template = registry.get("Supervisor")
    assert "sub_agents" in template.inputs
    field = template.inputs["sub_agents"]
    assert field.type == FieldType.MULTISELECT
    assert field.options_source == "agents.definitions"
    assert field.options_source in KNOWN_OPTIONS_SOURCES


def test_new_icon_is_in_the_allowlist(registry):
    """37.8 — SvgUserManage icon is in ICON_ALLOWLIST."""
    template = registry.get("Supervisor")
    assert template.icon in ICON_ALLOWLIST
    assert template.icon == "SvgUserManage"


@pytest.mark.asyncio
async def test_supervisor_requires_at_least_one_sub_agent(registry):
    """37.3 — Supervisor with empty sub_agents raises FlowBuildError."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "sup-1", "type": "Supervisor", "values": {"sub_agents": []}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "sup-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sup-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with pytest.raises(FlowBuildError, match="must declare at least one sub_agent"):
        await builder.build(spec)


@pytest.mark.asyncio
async def test_flow_builder_compiles_supervisor_via_build_async_sub_agent_ids(registry):
    """37.4 — FlowGraphBuilder compiles Supervisor by delegating to GraphBuilder.build_async."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "sup-1",
                    "type": "Supervisor",
                    "values": {"supervisor_prompt": "Lead team.", "sub_agents": ["c-1", "c-2"]},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "sup-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sup-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    mock_compiled = MagicMock()
    builder = FlowGraphBuilder(registry=registry)

    with (
        patch("domain.flows.resolvers.is_flow_backed", new_callable=AsyncMock) as mock_is_flow,
        patch(
            "agents.graphs.builder.GraphBuilder.build_async", new_callable=AsyncMock
        ) as mock_build_async,
    ):
        mock_is_flow.return_value = False
        mock_build_async.return_value = mock_compiled

        graph = await builder.build(spec)
        assert graph is not None
        assert mock_build_async.called
        schema_arg, config_arg = mock_build_async.call_args[0]
        assert schema_arg == "supervisor"
        assert config_arg["sub_agent_ids"] == ["c-1", "c-2"]
        assert config_arg["supervisor_prompt"] == "Lead team."


@pytest.mark.asyncio
async def test_supervisor_rejects_a_flow_backed_sub_agent(registry):
    """37.6 — Supervisor referencing a flow-backed agent raises FlowBuildError (§5.4)."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "sup-1", "type": "Supervisor", "values": {"sub_agents": ["flow-agent-id"]}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "sup-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sup-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with patch("domain.flows.resolvers.is_flow_backed", new_callable=AsyncMock) as mock_is_flow:
        mock_is_flow.return_value = True
        with pytest.raises(FlowBuildError, match="flow-backed"):
            await builder.build(spec)


@pytest.mark.asyncio
async def test_supervisor_uses_checkpointer_none_for_the_embedded_graph(registry):
    """37.7 — Embedded supervisor subgraph is constructed with checkpointer=None."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "sup-1", "type": "Supervisor", "values": {"sub_agents": ["c-1"]}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "sup-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sup-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with (
        patch("domain.flows.resolvers.is_flow_backed", new_callable=AsyncMock) as mock_is_flow,
        patch("agents.graphs.builder.GraphBuilder.__init__", return_value=None) as mock_gb_init,
        patch(
            "agents.graphs.builder.GraphBuilder.build_async", new_callable=AsyncMock
        ) as mock_build_async,
    ):
        mock_is_flow.return_value = False
        mock_build_async.return_value = MagicMock()
        await builder.build(spec)
        assert mock_gb_init.called
        kwargs = mock_gb_init.call_args.kwargs
        assert kwargs.get("checkpointer") is None


@pytest.mark.asyncio
async def test_supervisor_end_to_end_execution_through_flow(registry):
    """37.5 — End-to-end execution of a flow containing a Supervisor node."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "sup-1", "type": "Supervisor", "values": {"sub_agents": ["c-1"]}},
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "sup-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "sup-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    async def mock_supervisor_subgraph(state, config=None):
        return {"messages": [AIMessage(content="Delegated answer from supervisor team")]}

    builder = FlowGraphBuilder(registry=registry)
    with (
        patch("domain.flows.resolvers.is_flow_backed", new_callable=AsyncMock) as mock_is_flow,
        patch.object(builder, "_resolve_supervisor", new_callable=AsyncMock) as mock_resolve_sup,
    ):
        mock_is_flow.return_value = False
        mock_resolve_sup.return_value = mock_supervisor_subgraph

        graph = await builder.build(spec)
        res = await graph.ainvoke({"messages": [HumanMessage(content="Coordinate this task")]})
        assert len(res["messages"]) >= 1
        assert res["messages"][-1].content == "Delegated answer from supervisor team"
