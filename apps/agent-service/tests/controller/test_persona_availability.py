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
