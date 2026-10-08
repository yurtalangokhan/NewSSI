"""``/agents/{persona_id}/invoke`` (agent_interaction_service.invoke) gives the run the persona's connector access.

The coordinator used to re-query the persona for these; the run now takes them
from ``UserInput.server_config``, so the invoke service must supply them from the
persona it resolved."""

from __future__ import annotations

import pytest

from schemas.chat import UserInput
from service.orchestration import agent_interaction_service
from service.auth.auth_service import AuthenticatedUser
from service.orchestration.agent_runner_coordinator import _server_resolved_configurable
from service.orchestration.assistant_agent_service import AssistantAgentService


class _Stop(Exception):
    pass


@pytest.mark.asyncio
async def test_invoke_by_custom_persona_id_carries_connector_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    persona = {
        "is_builtin": False,
        "base_agent": "configurable-mcp-agent",
        "connector_bindings": [{"connection_id": "c-1", "tools": ["list_issues"]}],
    }

    class _Personas:
        async def get(self, _persona_id: int):
            return persona

    class _PersonaService:
        async def authorize_agent_execution(self, *_a, **_k) -> None:
            return None

    seen: list[UserInput] = []

    async def fake_handle_input(user_input, _agent, _user_id):
        seen.append(user_input)
        raise _Stop

    service = object.__new__(AssistantAgentService)

    async def fake_configured_agent(_agent_id, _config):
        return object()

    monkeypatch.setattr(service, "get_configured_agent", fake_configured_agent)
    monkeypatch.setattr(AssistantAgentService, "get_instance", classmethod(lambda cls: service))
    monkeypatch.setattr("service.orchestration.assistant_agent_service.persona_repository", lambda: _Personas())
    monkeypatch.setattr(agent_interaction_service, "get_persona_service", lambda: _PersonaService())
    monkeypatch.setattr(agent_interaction_service, "_handle_input", fake_handle_input)

    with pytest.raises(_Stop):
        await agent_interaction_service.invoke(
            AuthenticatedUser(user_id="u-1", email="u@example.com"),
            UserInput(message="hi"),
            "31",
        )

    run_config = _server_resolved_configurable(seen[0].server_config)
    assert run_config["connector_bindings"] == [{"connection_id": "c-1", "tools": ["list_issues"]}]
    assert run_config["binding_references"]["connectors.persona_id"] == "31"
