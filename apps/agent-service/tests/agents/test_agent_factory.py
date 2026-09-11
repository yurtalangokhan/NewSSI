"""Tests for the single, shared agent-construction factory.

Three existing call sites each independently decided "definition -> which
agent class": service/AgentHelpers.py, api/routes/AgentsRoute.py (the
isinstance check), service/AssistantAgentService.py. This factory is the one
place that decision is made now, so the branch isn't duplicated three times.

Spec: .tmp/flow-canvas-design.md section 6.2.
Brief: .tmp/flow-canvas-task-13-brief.md
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from agents.agent_factory import create_agent_for_definition
from agents.dynamic_agent import DynamicAgent
from agents.flow_agent import FlowAgent


@dataclass
class _FakeDefinition:
    id: str
    graph_schema: str
    flow_spec: dict | None = None
    persona_id: int | None = None
    created_by: str | None = None
    published_flow_version_id: str | None = None

    def to_config(self) -> dict:
        return {"name": "x", "graph_schema": self.graph_schema}


@pytest.mark.asyncio
async def test_factory_returns_flow_agent_for_flow_schema():
    definition = _FakeDefinition(id="d1", graph_schema="flow", flow_spec={"nodes": [], "edges": []})

    agent = await create_agent_for_definition(definition)

    assert isinstance(agent, FlowAgent)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schema", ["zero_shot", "react", "supervisor", "pipeline", "plan_execute", "self_reflect"]
)
async def test_factory_returns_dynamic_agent_for_classic_schemas(schema):
    """The constraint #1 assertion for this task: every existing schema
    still becomes a DynamicAgent, unchanged."""
    definition = _FakeDefinition(id="d2", graph_schema=schema)

    agent = await create_agent_for_definition(definition)

    assert isinstance(agent, DynamicAgent)


@pytest.mark.asyncio
async def test_flow_agent_owner_id_resolved_from_persona(monkeypatch):
    """A flow's send_email tool needs the flow owner's id. AgentDefinitionModel
    has no user_id column and created_by is never populated, so the owner must
    come from the linked persona."""
    from repository import persona_repository as PersonaRepository

    async def fake_get(persona_id):
        assert persona_id == 7
        return {"id": 7, "user_id": "owner-kc-sub"}

    monkeypatch.setattr(PersonaRepository.PersonaDB, "get", staticmethod(fake_get))

    definition = _FakeDefinition(
        id="d5", graph_schema="flow", flow_spec={"nodes": [], "edges": []}, persona_id=7
    )

    agent = await create_agent_for_definition(definition)

    assert agent._user_id == "owner-kc-sub"


@pytest.mark.asyncio
async def test_flow_agent_owner_id_falls_back_to_created_by(monkeypatch):
    from repository import persona_repository as PersonaRepository

    async def fake_get(persona_id):
        return None

    monkeypatch.setattr(PersonaRepository.PersonaDB, "get", staticmethod(fake_get))

    definition = _FakeDefinition(
        id="d6",
        graph_schema="flow",
        flow_spec={"nodes": [], "edges": []},
        persona_id=None,
        created_by="legacy-owner",
    )

    agent = await create_agent_for_definition(definition)

    assert agent._user_id == "legacy-owner"


@pytest.mark.asyncio
async def test_flow_agent_owner_id_survives_persona_lookup_error(monkeypatch):
    from repository import persona_repository as PersonaRepository

    async def boom(persona_id):
        raise RuntimeError("persona store down")

    monkeypatch.setattr(PersonaRepository.PersonaDB, "get", staticmethod(boom))

    definition = _FakeDefinition(
        id="d7",
        graph_schema="flow",
        flow_spec={"nodes": [], "edges": []},
        persona_id=7,
        created_by="legacy-owner",
    )

    agent = await create_agent_for_definition(definition)

    assert agent._user_id == "legacy-owner"


@pytest.mark.asyncio
async def test_flow_agent_has_no_version_when_nothing_is_published():
    definition = _FakeDefinition(id="d8", graph_schema="flow", flow_spec={"nodes": [], "edges": []})

    agent = await create_agent_for_definition(definition)

    assert agent.flow_version_no is None


@pytest.mark.asyncio
async def test_flow_agent_carries_the_published_version_no(monkeypatch):
    from repository import flow_version_repository

    class _Row:
        version_no = 5

    async def fake_get_published(self, definition_id):
        assert definition_id == "d9"
        return _Row()

    monkeypatch.setattr(
        flow_version_repository.FlowVersionRepository,
        "get_published",
        fake_get_published,
    )

    definition = _FakeDefinition(
        id="d9",
        graph_schema="flow",
        flow_spec={"nodes": [], "edges": []},
        published_flow_version_id="fv-uuid",
    )

    agent = await create_agent_for_definition(definition)

    assert agent.flow_version_no == 5


@pytest.mark.asyncio
async def test_factory_applies_checkpointer_to_flow_agent():
    definition = _FakeDefinition(id="d3", graph_schema="flow", flow_spec={"nodes": [], "edges": []})
    saver = object()

    agent = await create_agent_for_definition(definition, checkpointer=saver)

    assert agent._checkpointer is saver


@pytest.mark.asyncio
async def test_factory_applies_checkpointer_to_dynamic_agent():
    definition = _FakeDefinition(id="d4", graph_schema="react")
    saver = object()

    agent = await create_agent_for_definition(definition, checkpointer=saver)

    assert agent._checkpointer is saver
