"""Tests for PipelineStage template and compiler execution.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-38-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import _AGENT_SCHEMA_BY_TYPE, FlowGraphBuilder
from domain.flows.registry import get_registry
from models.flows import ComponentKind, FieldType, FlowSpec, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_pipeline_stage_template_registers(registry):
    """38.1 — PipelineStage registers with kind=EXECUTION, Message->Message, Model, Tools, Memory handles."""
    template = registry.get("PipelineStage")
    assert template is not None
    assert template.category == "agents"
    assert template.kind == ComponentKind.EXECUTION
    assert any(h.name == "input" and PortType.MESSAGE in h.types for h in template.handles.inputs)
    assert any(h.name == "model" and PortType.MODEL in h.types for h in template.handles.inputs)
    assert any(h.name == "tools" and PortType.TOOLS in h.types for h in template.handles.inputs)
    assert any(h.name == "output" and PortType.MESSAGE in h.types for h in template.handles.outputs)


def test_pipeline_stage_requires_a_name(registry):
    """38.2 — PipelineStage has required name field."""
    template = registry.get("PipelineStage")
    assert "name" in template.inputs
    field = template.inputs["name"]
    assert field.type == FieldType.STR
    assert field.required is True


def test_pipeline_stage_dispatches_through_the_react_schema():
    """38.3 — _AGENT_SCHEMA_BY_TYPE maps PipelineStage to react schema."""
    assert "PipelineStage" in _AGENT_SCHEMA_BY_TYPE
    schema = _AGENT_SCHEMA_BY_TYPE["PipelineStage"]
    assert str(schema.value if hasattr(schema, "value") else schema) == "react"


@pytest.mark.asyncio
async def test_flow_builder_compiles_a_pipeline_stage_node(registry):
    """38.4 — A flow with PipelineStage node compiles via ReAct agent compilation path."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "stage-1",
                    "type": "PipelineStage",
                    "values": {"name": "Parser", "system_prompt": "Parse JSON."},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "stage-1",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "stage-1",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    builder = FlowGraphBuilder(registry=registry)
    with patch(
        "agents.graphs.builder.GraphBuilder.build_async",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    ) as mock_gb_build:
        graph = await builder.build(spec)
        assert graph is not None
        assert mock_gb_build.called


@pytest.mark.asyncio
async def test_three_chained_pipeline_stages_execute_in_wired_order(registry):
    """38.5 — ChatInput -> Stage A -> Stage B -> Stage C -> ChatOutput executes sequentially."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "stage-a",
                    "type": "PipelineStage",
                    "values": {"name": "Step A", "system_prompt": "Step A"},
                },
                {
                    "id": "stage-b",
                    "type": "PipelineStage",
                    "values": {"name": "Step B", "system_prompt": "Step B"},
                },
                {
                    "id": "stage-c",
                    "type": "PipelineStage",
                    "values": {"name": "Step C", "system_prompt": "Step C"},
                },
                {"id": "out", "type": "ChatOutput"},
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "in",
                    "sourceHandle": "message",
                    "target": "stage-a",
                    "targetHandle": "input",
                },
                {
                    "id": "e2",
                    "source": "stage-a",
                    "sourceHandle": "output",
                    "target": "stage-b",
                    "targetHandle": "input",
                },
                {
                    "id": "e3",
                    "source": "stage-b",
                    "sourceHandle": "output",
                    "target": "stage-c",
                    "targetHandle": "input",
                },
                {
                    "id": "e4",
                    "source": "stage-c",
                    "sourceHandle": "output",
                    "target": "out",
                    "targetHandle": "message",
                },
            ],
        }
    )

    executed_stages = []

    def mock_make_node(node, resources, **kwargs):
        async def _run(state, config=None):
            if node.type == "PipelineStage":
                executed_stages.append(node.id)
            messages = list(state.get("messages", []))
            if node.type == "PipelineStage":
                messages.append(AIMessage(content=f"Done {node.id}"))
            return {"messages": messages}

        return _run

    builder = FlowGraphBuilder(registry=registry)
    with patch("agents.graphs.flow_builder.make_node", side_effect=mock_make_node):
        graph = await builder.build(spec)
        res = await graph.ainvoke({"messages": [HumanMessage(content="Start pipeline")]})
        assert executed_stages == ["stage-a", "stage-b", "stage-c"]
        assert len(res["messages"]) == 4  # 1 Human + 3 AI


def test_pipeline_stage_accepts_tools_handle(registry):
    """38.7 — PipelineStage declares tools input handle for tool wiring."""
    template = registry.get("PipelineStage")
    tools_handle = next((h for h in template.handles.inputs if h.name == "tools"), None)
    assert tools_handle is not None
    assert PortType.TOOLS in tools_handle.types
