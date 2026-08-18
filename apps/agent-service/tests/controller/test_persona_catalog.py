import pytest

from controller.persona_controller import PersonaController


def _custom_persona() -> dict:
    return {
        "id": 42,
        "name": "Research Agent",
        "description": "Researches documents",
        "labels": [{"id": 7, "name": "Research"}],
        "mcp_tools": ["web_search", "send_email"],
        "mcp_tool_configs": {"send_email": {"mail_config_id": "secret"}},
        "rag_config": {
            "document_processing": ["docs"],
            "knowledge_graph": ["graph"],
        },
        "starter_messages": [{"name": "Start", "message": "Summarize this"}],
        "llm_model_version_override": "llama3.1:8b",
        "llm_model_provider_override": "ollama",
        "uploaded_image_id": "image-1",
        "icon_name": "sparkles",
        "is_public": True,
        "display_priority": 10,
        "featured": True,
        "user_id": "owner-1",
        "user_email": "owner@example.com",
        "user_file_ids": ["file-1"],
        "users": [{"id": "user-1", "email": "user@example.com"}],
        "groups": [1, 2],
        "hierarchy_nodes": [{"id": 1}],
        "attached_documents": [{"id": "doc-1"}],
        "system_prompt": "hidden prompt",
        "replace_base_system_prompt": True,
        "task_prompt": "hidden task prompt",
        "datetime_aware": True,
        "base_agent": "chatbot",
        "long_term_memory": True,
        "search_start_date": "2026-01-01",
    }


@pytest.mark.asyncio
async def test_agent_catalog_summary_omits_detail_fields(monkeypatch) -> None:
    controller = PersonaController()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": [{"detail": "real check"}]}

    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    summary = await controller._serialize_custom_persona_summary(_custom_persona())

    assert summary["id"] == 42
    assert summary["name"] == "Research Agent"
    assert summary["owner"] == {"id": "owner-1", "email": "owner@example.com"}
    # The summary now surfaces the same real availability result as the
    # detail endpoint, instead of a hardcoded "available" placeholder.
    assert summary["availability"] == {
        "status": "available",
        "checks": [{"detail": "real check"}],
    }
    assert summary["action_count"] == 2
    assert summary["capabilities"] == {
        "has_actions": True,
        "has_conversation_starters": True,
        "has_retrieval": True,
        "has_web_search": True,
        "has_scoped_knowledge": True,
        "long_term_memory": True,
    }

    assert "system_prompt" not in summary
    assert "task_prompt" not in summary
    assert "mcp_tool_configs" not in summary
    assert "user_file_ids" not in summary
    assert "users" not in summary
    assert "groups" not in summary
    assert "hierarchy_nodes" not in summary
    assert "attached_documents" not in summary


@pytest.mark.asyncio
async def test_agent_catalog_summary_resolves_real_availability(monkeypatch) -> None:
    """The catalog summary must reflect real availability, not a hardcoded
    placeholder — otherwise cards can show "available" for an agent that the
    detail view (which does resolve real availability) reports as
    unavailable."""
    controller = PersonaController()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {
            "status": "unavailable",
            "checks": [
                {
                    "component": "model",
                    "status": "error",
                    "message": "Model 'llama3.1:8b' is selected but is not available.",
                }
            ],
        }

    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    summary = await controller._serialize_custom_persona_summary(_custom_persona())

    assert summary["availability"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_builtin_catalog_summary_resolves_real_availability(monkeypatch) -> None:
    controller = PersonaController()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {
            "status": "unavailable",
            "checks": [
                {
                    "component": "model",
                    "status": "error",
                    "message": "No default model is configured.",
                }
            ],
        }

    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    summary = await controller._serialize_builtin_persona_summary(
        0,
        "Chatbot",
        "Default chatbot",
        "chatbot",
    )

    assert summary["availability"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_agent_catalog_summary_does_not_load_dynamic_definition(monkeypatch) -> None:
    controller = PersonaController()
    persona = {**_custom_persona(), "base_agent": "dynamic-agent"}

    async def fail_dynamic_definition(_persona_id: int):
        raise AssertionError("catalog summary must not load dynamic definitions")

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": []}

    monkeypatch.setattr(controller, "_get_dynamic_definition", fail_dynamic_definition)
    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    summary = await controller._serialize_custom_persona_summary(persona)

    assert summary["is_dynamic"] is True
    assert "graph_schema" not in summary


@pytest.mark.asyncio
async def test_agent_catalog_summary_keeps_frontend_snapshot_fields(monkeypatch) -> None:
    controller = PersonaController()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": []}

    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability)

    summary = await controller._serialize_custom_persona_summary(_custom_persona())

    assert isinstance(summary["tools"], list)
    assert summary["starter_messages"] == [{"name": "Start", "message": "Summarize this"}]
    assert summary["document_sets"] == []
    assert summary["hierarchy_node_count"] == 0
    assert summary["attached_document_count"] == 0
    assert summary["knowledge_sources"] == []
    assert summary["llm_model_version_override"] == "llama3.1:8b"
    assert summary["llm_model_provider_override"] == "ollama"
    assert summary["mcp_tools"] == ["web_search", "send_email"]
