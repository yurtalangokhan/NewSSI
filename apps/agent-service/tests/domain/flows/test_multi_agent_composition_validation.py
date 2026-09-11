"""Tests enforcing section 5.4 invariant across every P6 surface.

Spec: .tmp/flow-canvas-design.md section 5.4.
Brief: .tmp/flow-canvas-task-39-brief.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from agents.graphs.flow_builder import FlowGraphBuilder
from api.routes.AgentDefinitionsRoute import _filter_available_agents_by_schema
from core.exceptions import FlowBuildError
from domain.agents.service import AgentDefinitionService
from domain.flows.registry import get_registry
from domain.flows.resolvers import ResolverContext, resolve_options
from domain.flows.validator import FLOW_NESTED_FLOW_REF, validate
from models.flows import FlowSpec
from service.CompositionValidationService import CompositionValidationService


@pytest.fixture
def registry():
    return get_registry()


@pytest.mark.asyncio
async def test_agents_definitions_resolver_excludes_flow_backed_still():
    """39.1 — Regression: agents.definitions resolver excludes flow-backed definitions."""
    with patch(
        "domain.agents.service.AgentDefinitionService.list_agent_definitions",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = [
            SimpleNamespace(id="c-1", name="Classic Agent", graph_schema="react"),
            SimpleNamespace(id="f-1", name="Flow Agent", graph_schema="flow"),
        ]
        options = await resolve_options("agents.definitions", ResolverContext(user_id="u-1"))
        assert [i.value for i in options.items] == ["c-1"]


def test_filter_available_agents_by_schema_excludes_flow_still():
    """39.2 — Regression: _filter_available_agents_by_schema excludes FLOW definitions."""
    agents = [
        {"id": "1", "name": "Classic ReAct", "graph_schema": "react"},
        {"id": "2", "name": "Flow Agent", "graph_schema": "flow"},
        {"id": "3", "name": "FLOW uppercase", "graph_schema": "FLOW"},
    ]
    filtered = _filter_available_agents_by_schema(agents, "SUPERVISOR")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "1"


def test_check_agent_ref_still_rejects_singular_agent_id():
    """39.3 — Regression: validator rejects singular flow-backed agent_id."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {"id": "aref-1", "type": "AgentRef", "values": {"agent_id": "flow-id"}},
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
    result = validate(spec, is_flow_backed=lambda aid: aid == "flow-id")
    assert not result.valid
    assert any(e.code == FLOW_NESTED_FLOW_REF and e.node_id == "aref-1" for e in result.errors)


@pytest.mark.asyncio
async def test_agent_ref_flow_builder_still_rejects_at_compile_time(registry):
    """39.4 — Regression: FlowGraphBuilder rejects flow-backed AgentRef at compile time."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "aref-1",
                    "type": "AgentRef",
                    "values": {"agent_id": "00000000-0000-0000-0000-000000000001"},
                },
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
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = SimpleNamespace(graph_schema="flow")
    builder = FlowGraphBuilder(registry=registry, repository=mock_repo)
    with pytest.raises(FlowBuildError, match="flow-backed"):
        await builder.build(spec)


def test_check_agent_ref_rejects_flow_backed_entry_inside_sub_agents_list():
    """39.5 — Hole 1: validator rejects flow-backed id inside sub_agents list."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "sup-1",
                    "type": "Supervisor",
                    "values": {"sub_agents": ["classic-id", "flow-id"]},
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
    result = validate(spec, is_flow_backed=lambda aid: aid == "flow-id")
    assert not result.valid
    assert any(e.code == FLOW_NESTED_FLOW_REF and e.node_id == "sup-1" for e in result.errors)


def test_check_agent_ref_passes_when_all_sub_agents_are_classic():
    """39.6 — validator passes when all sub_agents are classic agents."""
    spec = FlowSpec.model_validate(
        {
            "nodes": [
                {"id": "in", "type": "ChatInput"},
                {
                    "id": "sup-1",
                    "type": "Supervisor",
                    "values": {"sub_agents": ["classic-1", "classic-2"]},
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
    result = validate(spec, is_flow_backed=lambda aid: False)
    assert not any(e.code == FLOW_NESTED_FLOW_REF for e in result.errors)


@pytest.mark.asyncio
async def test_create_agent_definition_rejects_flow_backed_sub_agent_id():
    """39.7 — Hole 2 (create path): create_agent_definition rejects flow-backed sub_agent_ids."""
    flow_id = uuid4()
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = SimpleNamespace(
        id=flow_id, name="My Flow Agent", graph_schema="flow", sub_agent_ids=None
    )
    service = AgentDefinitionService(mock_repo)

    with pytest.raises(ValueError, match="flow-backed agents cannot be composed"):
        await service.create_agent_definition(
            name="Supervisor Agent",
            graph_schema="supervisor",
            sub_agent_ids=[flow_id],
        )


@pytest.mark.asyncio
async def test_update_sub_agents_rejects_flow_backed_sub_agent_id():
    """39.8 — Hole 2 (update sub-agents path): update_sub_agents rejects flow-backed sub_agent_ids."""
    master_id = uuid4()
    flow_id = uuid4()
    mock_repo = AsyncMock()

    def get_by_id_side_effect(uid):
        if uid == master_id:
            return SimpleNamespace(
                id=master_id,
                name="Supervisor",
                graph_schema="supervisor",
                sub_agent_ids=[],
                sub_agent_config_version=1,
            )
        if uid == flow_id:
            return SimpleNamespace(
                id=flow_id, name="Flow Agent", graph_schema="flow", sub_agent_ids=None
            )
        return None

    mock_repo.get_by_id.side_effect = get_by_id_side_effect
    service = AgentDefinitionService(mock_repo)

    with pytest.raises(ValueError, match="flow-backed agents cannot be composed"):
        await service.update_sub_agents(master_id, [flow_id])


@pytest.mark.asyncio
async def test_validate_composition_rejects_flow_backed_sub_agent_id():
    """39.9 — Hole 2 (validate composition endpoint): validate_full_composition returns error for flow sub-agents."""
    flow_id = uuid4()
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = SimpleNamespace(
        id=flow_id, name="Flow Agent", graph_schema="flow", sub_agent_ids=None
    )
    cvs = CompositionValidationService(mock_repo)
    result = await cvs.validate_full_composition(
        agent_id=None,
        graph_schema="supervisor",
        sub_agent_ids=[flow_id],
    )
    assert not result.valid
    assert any("flow-backed" in err for err in result.errors)


def test_pipeline_stage_has_no_agent_reference_field_to_guard(registry):
    """39.10 — PipelineStage has no agent reference input fields."""
    template = registry.get("PipelineStage")
    for field_name, field in template.inputs.items():
        assert field.options_source != "agents.definitions"
        assert field_name not in {"agent_id", "sub_agents", "sub_agent_ids"}
