from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from controller.persona_controller import PersonaController


def _persona(persona_id: int = 1) -> dict:
    return {"id": persona_id}


def test_dynamic_payload_preserves_existing_graph_schema_when_payload_omits_it():
    """A PATCH that doesn't resend graph_schema (a plain rename, e.g.) must
    not silently reset a flow-backed definition to "zero_shot" — that
    severs it from its flow_spec (agent_factory.py only builds a FlowAgent
    when graph_schema == "flow")."""
    controller = PersonaController()
    definition = SimpleNamespace(graph_schema="flow")

    result = controller._dynamic_payload_from_persona_payload(
        {"name": "Renamed agent"}, _persona(), definition
    )

    assert result["graph_schema"] == "flow"


def test_dynamic_payload_uses_explicit_graph_schema_over_existing_definition():
    controller = PersonaController()
    definition = SimpleNamespace(graph_schema="flow")

    result = controller._dynamic_payload_from_persona_payload(
        {"graph_schema": "react"}, _persona(), definition
    )

    assert result["graph_schema"] == "react"


def test_dynamic_payload_defaults_to_zero_shot_when_no_definition_exists():
    """Create path (no definition yet) keeps the original default."""
    controller = PersonaController()

    result = controller._dynamic_payload_from_persona_payload(
        {"name": "New agent"}, _persona(), None
    )

    assert result["graph_schema"] == "zero_shot"


@pytest.mark.asyncio
async def test_upsert_dynamic_definition_passes_existing_definition_through():
    controller = PersonaController()
    definition = SimpleNamespace(id="def-1", graph_schema="flow")
    repo = SimpleNamespace(get_by_persona_id=AsyncMock(return_value=definition))
    service = SimpleNamespace(update_agent_definition=AsyncMock())

    with (
        patch(
            "repository.agent_definition_repository.AgentDefinitionRepository", return_value=repo
        ),
        patch("domain.agents.service.AgentDefinitionService", return_value=service),
    ):
        await controller._upsert_dynamic_definition(
            {"base_agent": "dynamic-agent", "name": "Renamed agent"}, _persona()
        )

    service.update_agent_definition.assert_awaited_once()
    updated_payload = service.update_agent_definition.await_args.args[1]
    assert updated_payload["graph_schema"] == "flow"
