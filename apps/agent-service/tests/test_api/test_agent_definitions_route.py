"""Tests for agent definitions route helpers."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from api.routes.AgentDefinitionsRoute import (
    _filter_available_agents_by_schema,
    _normalize_schema_name,
    _serialize_definition_for_composition,
    expand_agent_definition_route,
)
from domain.flows.agent_expansion import AgentExpansionError
from models.flows import FlowEdge, FlowNode


def test_normalize_schema_name_case_insensitive() -> None:
    """Schema normalization should support lowercase frontend values."""
    assert _normalize_schema_name("supervisor") == "SUPERVISOR"
    assert _normalize_schema_name(" pipeline ") == "PIPELINE"


def test_filter_available_agents_by_schema_supervisor_lowercase() -> None:
    """Lowercase supervisor schema should return eligible nested agents."""
    agents = [
        {"id": "1", "graph_schema": "REACT"},
        {"id": "2", "graph_schema": "PLAN_EXECUTE"},
        {"id": "3", "graph_schema": "SUPERVISOR"},
        {"id": "4", "graph_schema": "PIPELINE"},
    ]

    filtered = _filter_available_agents_by_schema(agents, "supervisor")

    assert [agent["id"] for agent in filtered] == ["1", "2", "3"]


def test_filter_available_agents_by_schema_pipeline_lowercase() -> None:
    """Lowercase pipeline schema should exclude nested multi-agent schemas."""
    agents = [
        {"id": "1", "graph_schema": "REACT"},
        {"id": "2", "graph_schema": "PLAN_EXECUTE"},
        {"id": "3", "graph_schema": "SUPERVISOR"},
        {"id": "4", "graph_schema": "PIPELINE"},
        {"id": "5", "graph_schema": "ZERO_SHOT"},
    ]

    filtered = _filter_available_agents_by_schema(agents, "pipeline")

    assert [agent["id"] for agent in filtered] == ["1", "2", "5"]


def test_filter_available_agents_by_schema_excludes_flow_backed_agents() -> None:
    """Flows are not composable as sub-agents (design spec 5.4) — excluded
    regardless of which schema filter (or none) was requested."""
    agents = [
        {"id": "1", "graph_schema": "REACT"},
        {"id": "2", "graph_schema": "FLOW"},
    ]

    filtered_no_schema = _filter_available_agents_by_schema(agents, None)
    filtered_supervisor = _filter_available_agents_by_schema(agents, "supervisor")

    assert [agent["id"] for agent in filtered_no_schema] == ["1"]
    assert [agent["id"] for agent in filtered_supervisor] == ["1"]


@dataclass
class _FakeDefinition:
    id: object
    name: str
    graph_schema: str
    is_active: bool = True
    persona_id: int | None = None
    model: str | None = None
    mcp_tools: list | None = None
    memory_type: str | None = None
    system_prompt: str | None = None


def test_serialize_definition_for_composition_uses_persona_display_name() -> None:
    """The composition picker should show the real persona name, not the
    internal placeholder (e.g. "persona-15") stored on the definition."""
    definition_id = uuid4()
    d = _FakeDefinition(id=definition_id, name="persona-15", graph_schema="react", persona_id=15)

    result = _serialize_definition_for_composition(d, depth=0, persona_names={15: "Support Bot"})

    assert result["id"] == str(definition_id)
    assert result["name"] == "Support Bot"


def test_serialize_definition_for_composition_falls_back_without_persona_link() -> None:
    d = _FakeDefinition(id=uuid4(), name="Manual Definition", graph_schema="react", persona_id=None)

    result = _serialize_definition_for_composition(d, depth=0, persona_names={})

    assert result["name"] == "Manual Definition"


def test_serialize_definition_for_composition_includes_hover_preview() -> None:
    d = _FakeDefinition(
        id=uuid4(),
        name="persona-7",
        graph_schema="react",
        persona_id=7,
        model="gpt-4o",
        mcp_tools=["file_read"],
        memory_type="long_term",
    )

    result = _serialize_definition_for_composition(d, depth=0, persona_names={7: "Research Agent"})

    assert "gpt-4o" in result["preview"]
    assert "Tools: 1" in result["preview"]


@pytest.mark.asyncio
async def test_expand_route_returns_serialized_nodes_and_edges():
    node = FlowNode(
        id="n1", type="ReActAgent", values={"system_prompt": "hi"}, position={"x": 0, "y": 0}
    )
    edge = FlowEdge(id="e1", source="n0", sourceHandle="model", target="n1", targetHandle="model")

    with patch(
        "api.routes.AgentDefinitionsRoute.expand_agent_definition",
        new_callable=AsyncMock,
        return_value=([node], [edge]),
    ):
        result = await expand_agent_definition_route(definition_id="n1", _user={"id": "u1"})

    assert result["nodes"][0]["id"] == "n1"
    assert result["edges"][0]["sourceHandle"] == "model"


@pytest.mark.asyncio
async def test_expand_route_maps_expansion_error_to_400():
    from fastapi import HTTPException

    with patch(
        "api.routes.AgentDefinitionsRoute.expand_agent_definition",
        new_callable=AsyncMock,
        side_effect=AgentExpansionError("nope"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await expand_agent_definition_route(definition_id="n1", _user={"id": "u1"})

    assert exc_info.value.status_code == 400
