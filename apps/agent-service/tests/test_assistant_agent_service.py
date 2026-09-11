import pytest

from service.AssistantAgentService import AssistantAgentService


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

    monkeypatch.setattr("repository.persona_repository.PersonaDB.get", fake_get)
    monkeypatch.setattr(service, "get_assistant", fake_get_assistant)

    graph_id, config = await service.get_graph_and_config(19)

    assert graph_id == "chatbot"
    assert config == {}


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

    class FakeDefinitionRepository:
        async def get_by_persona_id(self, persona_id: int):
            assert persona_id == 23
            return FakeDefinition()

    monkeypatch.setattr("repository.persona_repository.PersonaDB.get", fake_get)
    monkeypatch.setattr(
        "repository.agent_definition_repository.AgentDefinitionRepository",
        FakeDefinitionRepository,
    )

    graph_id, config = await service.get_graph_and_config(23)

    assert graph_id == "definition-1"
    assert config["owner_user_id"] == "owner-user"
