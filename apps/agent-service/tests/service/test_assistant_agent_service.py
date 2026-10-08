import pytest

from service.orchestration.assistant_agent_service import AssistantAgentService


@pytest.mark.asyncio
async def test_get_graph_and_config_accepts_numeric_agent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(AssistantAgentService)

    async def fake_get(persona_id: int):
        assert persona_id == 19
        return {
            "is_builtin": False,
            "base_agent": "chatbot",
            "mcp_tools": [],
            "rag_config": {},
        }

    async def fake_get_assistant(_assistant_id: str):
        return None

    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        staticmethod(fake_get),
    )
    monkeypatch.setattr(service, "get_assistant", fake_get_assistant)

    graph_id, config = await service.get_graph_and_config(19)

    assert graph_id == "chatbot"
    assert config == {
        "connector_bindings": [],
        "binding_references": {"connectors.persona_id": "19"},
        "_persona_id": 19,
    }


@pytest.mark.asyncio
async def test_get_graph_and_config_preserves_dynamic_persona_owner_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(AssistantAgentService)

    async def fake_get(persona_id: int):
        assert persona_id == 23
        return {
            "is_builtin": False,
            "user_id": "owner-user",
            "base_agent": "dynamic-agent",
            "mcp_tools": ["send_email"],
            "mcp_tool_configs": {"send_email": {"mail_config_id": "mail-config-1"}},
            "rag_config": {},
        }

    class FakeDefinition:
        id = "definition-1"

        def to_config(self):
            return {
                "mcp_tools": ["send_email"],
                "mcp_tool_configs": {"send_email": {"mail_config_id": "mail-config-1"}},
            }

    class _FakeDefinitionRows:
        async def get_by_persona_id(self, persona_id: int):
            assert persona_id == 23
            return FakeDefinition()

    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        staticmethod(fake_get),
    )
    monkeypatch.setattr(
        "infrastructure.db.repositories.agent_definition_repo.AgentDefinitionRepository",
        _FakeDefinitionRows,
    )

    graph_id, config = await service.get_graph_and_config(23)

    assert graph_id == "definition-1"
    assert config["owner_user_id"] == "owner-user"


def _patch_persona(monkeypatch: pytest.MonkeyPatch, persona: dict, *, definition=None) -> AssistantAgentService:
    service = object.__new__(AssistantAgentService)

    class _Personas:
        async def get(self, _persona_id: int):
            return persona

    class _Definitions:
        async def get_by_persona_id(self, _persona_id: int):
            return definition

    monkeypatch.setattr("service.orchestration.assistant_agent_service.persona_repository", lambda: _Personas())
    monkeypatch.setattr(
        "service.orchestration.assistant_agent_service.agent_definition_repository", lambda: _Definitions()
    )
    return service


@pytest.mark.asyncio
async def test_get_graph_and_config_emits_connector_bindings_for_custom_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _patch_persona(
        monkeypatch,
        {
            "is_builtin": False,
            "base_agent": "configurable-mcp-agent",
            "system_prompt": "Persona prompt",
            "connector_bindings": [{"connection_id": "c-1", "tools": ["list_issues"]}],
            "rag_config": {"document_processing": ["col-1"]},
        },
    )

    graph_id, config = await service.get_graph_and_config(31)

    assert graph_id == "configurable-mcp-agent"
    assert config["connector_bindings"] == [{"connection_id": "c-1", "tools": ["list_issues"]}]
    assert config["binding_references"]["connectors.persona_id"] == "31"
    assert config["system_prompt"] == "Persona prompt"
    assert config["rag_config"] == {"document_processing": ["col-1"]}


@pytest.mark.asyncio
async def test_get_graph_and_config_dynamic_persona_carries_persona_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Definition:
        id = "definition-9"

        def to_config(self):
            return {
                "model": "m-1",
                "system_prompt": "Definition prompt",
                "rag_config": {"document_processing": ["stale"]},
                "memory_type": "long_term",
            }

    service = _patch_persona(
        monkeypatch,
        {
            "is_builtin": False,
            "user_id": "owner-1",
            "base_agent": "dynamic-agent",
            "system_prompt": "Persona prompt",
            "rag_config": {"document_processing": ["col-1"]},
            "connector_bindings": [{"connection_id": "c-1", "tools": ["list_issues"]}],
        },
        definition=_Definition(),
    )

    graph_id, config = await service.get_graph_and_config(31)

    assert graph_id == "definition-9"
    assert config["system_prompt"] == "Persona prompt"
    assert config["rag_config"] == {"document_processing": ["col-1"]}
    assert config["model"] == "m-1"
    assert config["memory_type"] == "long_term"
    assert config["owner_user_id"] == "owner-1"
    assert config["connector_bindings"] == [{"connection_id": "c-1", "tools": ["list_issues"]}]
    assert config["binding_references"]["connectors.persona_id"] == "31"
