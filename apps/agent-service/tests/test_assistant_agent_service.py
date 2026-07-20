import pytest

from service.AssistantAgentService import AssistantAgentService


@pytest.mark.asyncio
async def test_get_graph_and_config_accepts_numeric_agent_id(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr("service.PersonaRepository.PersonaDB.get", fake_get)
    monkeypatch.setattr(service, "get_assistant", fake_get_assistant)

    graph_id, config = await service.get_graph_and_config(19)

    assert graph_id == "chatbot"
    assert config == {}
