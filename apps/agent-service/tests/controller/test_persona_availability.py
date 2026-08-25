import pytest

from controller.persona_controller import PersonaController, build_agent_availability


class _DynamicDefinition:
    graph_schema = "react"
    brain_type = "llm"
    memory_type = "none"
    mcp_tools = []
    rag_config = {"document_processing": [], "knowledge_graph": []}
    sub_agent_ids = []
    sub_agents = []
    supervisor_prompt = None
    stages = []
    pipeline_prompt = None
    reflection_prompt = None
    max_iterations = 3
    model = "missing-model"


def test_custom_model_missing_makes_agent_unavailable() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": "gpt-4o",
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        memory_available=True,
    )

    assert availability["status"] == "unavailable"
    assert availability["checks"][0] == {
        "component": "model",
        "status": "error",
        "message": "Model 'gpt-4o' is selected but is not available.",
    }


def test_default_model_ollama_alias_resolves_to_available_model() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": None,
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="ollama",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        memory_available=True,
    )

    assert availability["status"] == "available"
    assert availability["checks"][0] == {
        "component": "model",
        "status": "ok",
        "message": "Using default model 'llama3.1:8b'.",
    }


def test_agent_with_ollama_model_override_resolves_to_concrete_model() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": "ollama",
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        memory_available=True,
    )

    assert availability["status"] == "available"
    assert availability["checks"][0] == {
        "component": "model",
        "status": "ok",
        "message": "Model 'llama3.1:8b' is available.",
    }


def test_default_model_uses_default_model_availability() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": None,
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        memory_available=True,
    )

    assert availability["status"] == "available"
    assert availability["checks"][0]["message"] == "Using default model 'llama3.1:8b'."


def test_missing_components_are_reported() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": "llama3.1:8b",
            "mcp_tools": ["github_search", "slack_search"],
            "rag_config": {
                "document_processing": ["docs"],
                "knowledge_graph": ["graph-docs"],
            },
            "memory_type": "long_term",
            "long_term_memory": True,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools={"github_search"},
        available_rag_collections=set(),
        available_graph_rag_collections={"graph-docs"},
        memory_available=False,
    )

    assert availability["status"] == "unavailable"
    assert {
        "component": "memory",
        "status": "error",
        "message": "Long-term memory is enabled but memory storage is not available.",
    } in availability["checks"]
    assert {
        "component": "mcp_tool",
        "status": "error",
        "message": "MCP tool 'slack_search' is selected but is not available.",
    } in availability["checks"]
    assert {
        "component": "rag",
        "status": "error",
        "message": "RAG collection 'docs' is selected but is not available.",
    } in availability["checks"]


def test_rag_collection_messages_use_display_names() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": "llama3.1:8b",
            "mcp_tools": [],
            "rag_config": {
                "document_processing": ["9f2cd352-f3ea-4c63-8e2b-13a676569602"],
                "knowledge_graph": ["graph-collection-id"],
            },
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        collection_display_names={
            "9f2cd352-f3ea-4c63-8e2b-13a676569602": "Product Docs",
            "graph-collection-id": "Support Graph",
        },
        memory_available=True,
    )

    assert {
        "component": "rag",
        "status": "error",
        "message": "RAG collection 'Product Docs' is selected but is not available.",
    } in availability["checks"]
    assert {
        "component": "graph_rag",
        "status": "error",
        "message": "Graph RAG collection 'Support Graph' is selected but is not available.",
    } in availability["checks"]


def test_rag_collection_messages_use_rag_config_display_name_snapshot() -> None:
    availability = build_agent_availability(
        {
            "llm_model_version_override": "llama3.1:8b",
            "mcp_tools": [],
            "rag_config": {
                "document_processing": ["9f2cd352-f3ea-4c63-8e2b-13a676569602"],
                "knowledge_graph": [],
                "display_names": {
                    "9f2cd352-f3ea-4c63-8e2b-13a676569602": "Archived Docs",
                },
            },
            "memory_type": "none",
            "long_term_memory": False,
        },
        available_models={"llama3.1:8b"},
        default_model="llama3.1:8b",
        available_mcp_tools=set(),
        available_rag_collections=set(),
        available_graph_rag_collections=set(),
        memory_available=True,
    )

    assert {
        "component": "rag",
        "status": "error",
        "message": "RAG collection 'Archived Docs' is selected but is not available.",
    } in availability["checks"]


@pytest.mark.asyncio
async def test_serialized_dynamic_persona_includes_model_availability(monkeypatch) -> None:
    controller = PersonaController()

    async def fake_dynamic_definition(_persona_id: int):
        return _DynamicDefinition()

    async def fake_availability_context(agent: dict):
        return build_agent_availability(
            agent,
            available_models={"llama3.1:8b"},
            default_model="llama3.1:8b",
            available_mcp_tools=set(),
            available_rag_collections=set(),
            available_graph_rag_collections=set(),
            memory_available=True,
        )

    monkeypatch.setattr(controller, "_get_dynamic_definition", fake_dynamic_definition)
    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability_context)

    serialized = await controller._serialize_custom_persona(
        {
            "id": 10,
            "name": "Agent",
            "description": "Test agent",
            "base_agent": "dynamic-agent",
            "llm_model_version_override": None,
            "llm_model_provider_override": None,
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "long_term_memory": False,
            "is_public": True,
        }
    )

    assert serialized["llm_model_version_override"] == "missing-model"
    assert serialized["availability"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_serialized_builtin_persona_includes_availability(monkeypatch) -> None:
    controller = PersonaController()

    async def fake_availability_context(agent: dict):
        return build_agent_availability(
            agent,
            available_models={"llama3.1:8b"},
            default_model="llama3.1:8b",
            available_mcp_tools=set(),
            available_rag_collections=set(),
            available_graph_rag_collections=set(),
            memory_available=True,
        )

    monkeypatch.setattr(controller, "_get_agent_availability", fake_availability_context)

    serialized = await controller._serialize_builtin_persona(
        0,
        "Chatbot",
        "Default chatbot",
        "chatbot",
    )

    assert serialized["availability"]["status"] == "available"


@pytest.mark.asyncio
async def test_availability_uses_rag_service_for_graph_collections(monkeypatch) -> None:
    controller = PersonaController()
    graph_id = "8d5f9e92-0ff8-4bdf-8c53-e5625df314ef"

    async def fake_local_collection_info(collection_ids: list[str], *, source_key: str, cache=None):
        return set(), {}

    async def fake_fetch_payload():
        return {"knowledge_graph": [{"id": graph_id, "name": "Telekomünikasyon"}]}

    async def fake_model_names():
        return {"llama3.1:8b"}

    async def fake_tool_names():
        return set()

    monkeypatch.setattr(
        controller,
        "_get_local_collection_info",
        fake_local_collection_info,
    )
    monkeypatch.setattr(
        controller,
        "_fetch_rag_knowledge_selector_payload",
        fake_fetch_payload,
    )
    monkeypatch.setattr(
        controller,
        "_get_available_model_names",
        fake_model_names,
    )
    monkeypatch.setattr(controller, "_get_available_mcp_tool_names", fake_tool_names)
    monkeypatch.setattr(controller, "_is_memory_available", lambda: True)
    monkeypatch.setattr(
        "controller.persona_controller.settings.DEFAULT_MODEL",
        "llama3.1:8b",
    )

    availability = await controller._get_agent_availability(
        {
            "rag_config": {
                "document_processing": [],
                "knowledge_graph": [graph_id],
            },
            "mcp_tools": [],
            "memory_type": "none",
            "long_term_memory": False,
        }
    )

    assert availability["status"] == "available"
    assert {
        "component": "graph_rag",
        "status": "ok",
        "message": "Graph RAG collection 'Telekomünikasyon' is available.",
    } in availability["checks"]


@pytest.mark.asyncio
async def test_catalog_fetches_rag_payload_once_for_all_agents(monkeypatch) -> None:
    """The catalog list must not call the RAG service once per agent."""
    controller = PersonaController()
    graph_id = "8d5f9e92-0ff8-4bdf-8c53-e5625df314ef"

    fetch_calls = 0

    async def fake_fetch_payload():
        nonlocal fetch_calls
        fetch_calls += 1
        return {"knowledge_graph": [{"id": graph_id, "name": "Shared KB"}]}

    async def fake_local_collection_info(collection_ids, *, source_key, cache=None):
        return set(), {}

    async def fake_model_names():
        return {"llama3.1:8b"}

    async def fake_tool_metadata():
        return {}

    monkeypatch.setattr(controller, "_fetch_rag_knowledge_selector_payload", fake_fetch_payload)
    monkeypatch.setattr(controller, "_get_local_collection_info", fake_local_collection_info)
    monkeypatch.setattr(controller, "_get_available_model_names", fake_model_names)
    monkeypatch.setattr(controller, "_get_mcp_tool_metadata", fake_tool_metadata)
    monkeypatch.setattr(controller, "_is_memory_available", lambda: True)
    monkeypatch.setattr(
        "controller.persona_controller.settings.DEFAULT_MODEL",
        "llama3.1:8b",
    )

    async def fake_list_all(include_builtin: bool = False):
        return [
            {
                "id": idx,
                "name": f"Agent {idx}",
                "description": "",
                "rag_config": {
                    "document_processing": [],
                    "knowledge_graph": [graph_id],
                },
                "mcp_tools": [],
                "long_term_memory": False,
                "user_id": None,
            }
            for idx in range(5)
        ]

    monkeypatch.setattr(
        "controller.persona_controller.PersonaDB.list_all",
        fake_list_all,
    )

    async def fake_load_owner_emails(personas):
        return {}

    monkeypatch.setattr(controller, "_load_owner_emails", fake_load_owner_emails)

    agents = await controller.get_agent_catalog(user=None)

    assert fetch_calls == 1
    custom_agents = [agent for agent in agents if not agent.get("builtin_persona")]
    assert len(custom_agents) == 5
    assert all(agent["availability"]["status"] == "available" for agent in custom_agents)


@pytest.mark.asyncio
async def test_catalog_fetches_mcp_tool_metadata_once_and_uses_real_descriptions(
    monkeypatch,
) -> None:
    """The catalog list must not call the MCP tool catalog once per agent,
    and the descriptions it fetches must reach each agent's tool snapshots
    (used by the frontend's per-tool info icon)."""
    controller = PersonaController()

    metadata_calls = 0

    async def fake_tool_metadata():
        nonlocal metadata_calls
        metadata_calls += 1
        return {
            "web_search": {
                "description": "Searches the live web for current information.",
                "display_name": "",
            }
        }

    async def fake_model_names():
        return {"llama3.1:8b"}

    monkeypatch.setattr(controller, "_get_mcp_tool_metadata", fake_tool_metadata)
    monkeypatch.setattr(controller, "_get_available_model_names", fake_model_names)
    monkeypatch.setattr(controller, "_is_memory_available", lambda: True)
    monkeypatch.setattr(
        "controller.persona_controller.settings.DEFAULT_MODEL",
        "llama3.1:8b",
    )

    async def fake_list_all(include_builtin: bool = False):
        return [
            {
                "id": idx,
                "name": f"Agent {idx}",
                "description": "",
                "rag_config": {"document_processing": [], "knowledge_graph": []},
                "mcp_tools": ["web_search"],
                "long_term_memory": False,
                "user_id": None,
            }
            for idx in range(3)
        ]

    monkeypatch.setattr(
        "controller.persona_controller.PersonaDB.list_all",
        fake_list_all,
    )

    async def fake_load_owner_emails(personas):
        return {}

    monkeypatch.setattr(controller, "_load_owner_emails", fake_load_owner_emails)

    agents = await controller.get_agent_catalog(user=None)

    assert metadata_calls == 1
    custom_agents = [agent for agent in agents if not agent.get("builtin_persona")]
    assert len(custom_agents) == 3
    for agent in custom_agents:
        web_search_tool = next(t for t in agent["tools"] if t["name"] == "web_search")
        assert web_search_tool["description"] == "Searches the live web for current information."
