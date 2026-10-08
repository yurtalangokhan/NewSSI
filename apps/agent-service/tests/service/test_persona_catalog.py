import pytest
from localization import set_locale

from service.personas.persona_service import PersonaService, _parse_mcp_tool_description


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


async def _fake_tool_metadata() -> dict:
    return {}


@pytest.mark.asyncio
async def test_agent_catalog_summary_omits_detail_fields(monkeypatch) -> None:
    service = PersonaService()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": [{"detail": "real check"}]}

    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)
    monkeypatch.setattr(service, "_get_mcp_tool_metadata", _fake_tool_metadata)

    summary = await service._serialize_custom_persona_summary(_custom_persona())

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
    service = PersonaService()

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

    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)
    monkeypatch.setattr(service, "_get_mcp_tool_metadata", _fake_tool_metadata)

    summary = await service._serialize_custom_persona_summary(_custom_persona())

    assert summary["availability"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_builtin_catalog_summary_resolves_real_availability(monkeypatch) -> None:
    service = PersonaService()

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

    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)

    summary = await service._serialize_builtin_persona_summary(
        0,
        "Chatbot",
        "Default chatbot",
        "chatbot",
    )

    assert summary["availability"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_agent_catalog_summary_does_not_load_dynamic_definition(monkeypatch) -> None:
    service = PersonaService()
    persona = {**_custom_persona(), "base_agent": "dynamic-agent"}

    async def fail_dynamic_definition(_persona_id: int):
        raise AssertionError("catalog summary must not load dynamic definitions")

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": []}

    monkeypatch.setattr(service, "_get_dynamic_definition", fail_dynamic_definition)
    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)
    monkeypatch.setattr(service, "_get_mcp_tool_metadata", _fake_tool_metadata)

    summary = await service._serialize_custom_persona_summary(persona)

    assert summary["is_dynamic"] is True
    assert "graph_schema" not in summary


@pytest.mark.asyncio
async def test_agent_catalog_summary_keeps_frontend_snapshot_fields(monkeypatch) -> None:
    service = PersonaService()

    async def fake_availability(_agent: dict, **_kwargs) -> dict:
        return {"status": "available", "checks": []}

    monkeypatch.setattr(service, "_get_agent_availability", fake_availability)
    monkeypatch.setattr(service, "_get_mcp_tool_metadata", _fake_tool_metadata)

    summary = await service._serialize_custom_persona_summary(_custom_persona())

    assert isinstance(summary["tools"], list)
    assert summary["starter_messages"] == [{"name": "Start", "message": "Summarize this"}]
    assert summary["document_sets"] == []
    assert summary["hierarchy_node_count"] == 0
    assert summary["attached_document_count"] == 0
    assert summary["knowledge_sources"] == []
    assert summary["llm_model_version_override"] == "llama3.1:8b"
    assert summary["llm_model_provider_override"] == "ollama"
    assert summary["mcp_tools"] == ["web_search", "send_email"]


def test_tool_snapshots_use_real_mcp_tool_descriptions_when_provided() -> None:
    """Frontend shows the description behind an info icon — it must not be
    the hardcoded empty string every synthetic tool used to get."""
    service = PersonaService()

    snapshots = service._build_tool_snapshots(
        persona_id=1,
        mcp_tool_names=["web_search", "send_email"],
        rag_config=None,
        tool_descriptions={
            "web_search": {
                "description": "Searches the live web for current information.",
                "display_name": "",
            }
        },
    )

    by_name = {snap["name"]: snap for snap in snapshots}
    assert by_name["web_search"]["description"] == "Searches the live web for current information."
    # No description available for send_email: falls back to empty, not an error.
    assert by_name["send_email"]["description"] == ""


def test_tool_snapshots_default_rag_tool_descriptions() -> None:
    """database_search/graph_search have no external source for a
    description (they're synthesized from the agent's RAG config, not a
    real MCP tool), so they need a sensible built-in description."""
    service = PersonaService()

    snapshots = service._build_tool_snapshots(
        persona_id=1,
        mcp_tool_names=[],
        rag_config={
            "document_processing": ["collection-1"],
            "knowledge_graph": ["collection-2"],
        },
    )

    by_name = {snap["name"]: snap for snap in snapshots}
    assert by_name["database_search"]["description"]
    assert by_name["graph_search"]["description"]
    assert by_name["database_search"]["description"] != by_name["graph_search"]["description"]


def test_tool_snapshots_use_locale_for_rag_tool_names_and_descriptions() -> None:
    """The RAG-derived tools' name/description must follow the request's
    language like everything else, not stay hardcoded English."""
    service = PersonaService()

    set_locale("tr")
    try:
        snapshots = service._build_tool_snapshots(
            persona_id=1,
            mcp_tool_names=[],
            rag_config={"document_processing": ["collection-1"], "knowledge_graph": []},
        )
    finally:
        set_locale("en")

    database_search = next(s for s in snapshots if s["name"] == "database_search")
    assert database_search["display_name"] == "Veri Tabanı Arama"
    assert database_search["description"] == "Bu ajana bağlı belgelerde arama yapar."


def test_tool_snapshots_one_per_rag_collection_with_display_names() -> None:
    """Each assigned RAG collection must surface as its own tool entry, named
    after the collection — not collapse into one generic placeholder per RAG
    kind, which is all the chat input bar's tools popover had to show."""
    service = PersonaService()

    snapshots = service._build_tool_snapshots(
        persona_id=1,
        mcp_tool_names=[],
        rag_config={
            "document_processing": ["col-1", "col-2"],
            "knowledge_graph": ["col-3"],
            "display_names": {
                "col-1": "Quantum Physics",
                "col-2": "Company Policies",
                "col-3": "Org Chart",
            },
        },
    )

    doc_snapshots = [s for s in snapshots if s["name"] == "database_search"]
    graph_snapshots = [s for s in snapshots if s["name"] == "graph_search"]
    assert {s["display_name"] for s in doc_snapshots} == {"Quantum Physics", "Company Policies"}
    assert {s["display_name"] for s in graph_snapshots} == {"Org Chart"}
    assert len({s["id"] for s in snapshots}) == len(snapshots)


def test_tool_snapshots_read_the_legacy_collections_key_as_documents() -> None:
    service = PersonaService()

    snapshots = service._build_tool_snapshots(
        persona_id=1,
        mcp_tool_names=[],
        rag_config={"collections": ["legacy-1", "legacy-2"]},
    )

    assert [s["name"] for s in snapshots] == ["database_search", "database_search"]


def test_tool_snapshots_rag_collection_without_display_name_falls_back() -> None:
    """A collection missing from rag_config.display_names must still get a
    usable label instead of disappearing or crashing."""
    service = PersonaService()

    snapshots = service._build_tool_snapshots(
        persona_id=1,
        mcp_tool_names=[],
        rag_config={"document_processing": ["col-1"], "knowledge_graph": [], "display_names": {}},
    )

    assert len(snapshots) == 1
    assert snapshots[0]["display_name"]


def test_parse_mcp_tool_description_strips_category_and_title_tags() -> None:
    """tools-service embeds [category:...][category_label:...][title:...]
    tags directly in the description string (see
    apps/tools-service/src/core/registry.py). Users must never see the raw
    tags — this is exactly what was reported: an agent's tool showed
    "[category:web_search][category_label:Web][title:Web'de Ara] SearXNG
    arama motorunu kullanarak web'de arama yapın." verbatim."""
    raw = (
        "[category:web_search][category_label:Web][title:Web'de Ara] "
        "SearXNG arama motorunu kullanarak web'de arama yapın."
    )

    clean_description, title = _parse_mcp_tool_description(raw)

    assert clean_description == "SearXNG arama motorunu kullanarak web'de arama yapın."
    assert title == "Web'de Ara"
    assert "[" not in clean_description


def test_parse_mcp_tool_description_handles_plain_description() -> None:
    """A description with no tags at all (e.g. a custom MCP provider that
    doesn't go through tools-service's i18n wrapper) must pass through
    unchanged, with no title."""
    clean_description, title = _parse_mcp_tool_description("Sends an email.")

    assert clean_description == "Sends an email."
    assert title is None


@pytest.mark.asyncio
async def test_get_mcp_tool_metadata_uses_title_tag_as_display_name(monkeypatch) -> None:
    """End-to-end: the raw tools-service payload (tags and all) must come
    out of _get_mcp_tool_metadata as a clean description plus a localized
    display name, ready for the frontend's info icon and tool label."""
    service = PersonaService()

    class _FakeMCPToolService:
        @classmethod
        def get_instance(cls):
            return cls()

        async def list_tools(self, include_inactive: bool = False):
            return []

    async def fake_get_builtin_mcp_tools(_url):
        return {
            "tools": [
                {
                    "name": "web_search",
                    "description": (
                        "[category:web_search][category_label:Web][title:Web'de Ara] "
                        "SearXNG arama motorunu kullanarak web'de arama yapın."
                    ),
                }
            ]
        }

    monkeypatch.setattr("service.mcp.mcp_tool_service.MCPToolService", _FakeMCPToolService)

    class _FakeProxyService:
        async def get_builtin_mcp_tools(self, url):
            return await fake_get_builtin_mcp_tools(url)

    monkeypatch.setattr(
        "service.proxy.proxy_service.get_proxy_service",
        lambda: _FakeProxyService(),
    )

    metadata = await service._get_mcp_tool_metadata()

    assert metadata["web_search"]["display_name"] == "Web'de Ara"
    assert (
        metadata["web_search"]["description"]
        == "SearXNG arama motorunu kullanarak web'de arama yapın."
    )
