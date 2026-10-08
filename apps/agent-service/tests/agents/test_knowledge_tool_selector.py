"""Knowledge tool selection for the tools-service ownership model."""

from agents.knowledge.tool_selector import (
    KnowledgeToolSelector,
    build_knowledge_binding_references,
)


def test_select_tool_names_maps_rag_config_to_tools_service_names() -> None:
    selected = KnowledgeToolSelector.select_tool_names(
        {
            "document_processing": ["docs-1"],
            "knowledge_graph": ["graph-1"],
        }
    )

    assert selected == ["database_search", "graph_search"]


def test_select_tools_returns_no_local_tool_implementations() -> None:
    assert KnowledgeToolSelector.select_tools({"document_processing": ["docs-1"]}) == []


def test_select_collections_groups_collection_ids_by_tool() -> None:
    assert KnowledgeToolSelector.select_collections(
        {"document_processing": ["docs-1", "docs-2"], "knowledge_graph": ["graph-1"]}
    ) == {"database_search": ["docs-1", "docs-2"], "graph_search": ["graph-1"]}


def test_select_collections_reads_the_legacy_collections_key_as_documents() -> None:
    rag_config = {"collections": ["legacy-1"]}

    assert KnowledgeToolSelector.select_collections(rag_config) == {
        "database_search": ["legacy-1"]
    }
    assert KnowledgeToolSelector.select_tool_names(rag_config) == ["database_search"]


def test_select_collections_prefers_document_processing_over_legacy_key() -> None:
    assert KnowledgeToolSelector.select_collections(
        {"document_processing": ["docs-1"], "collections": ["legacy-1"]}
    ) == {"database_search": ["docs-1"]}


def test_binding_references_use_one_dotted_key_per_selected_tool() -> None:
    references = build_knowledge_binding_references(
        {"document_processing": ["docs-1"], "knowledge_graph": ["graph-1"]}
    )

    assert references == {
        "database_search.collection_ids": '["docs-1"]',
        "graph_search.collection_ids": '["graph-1"]',
    }


def test_binding_references_omit_the_graph_key_without_graph_collections() -> None:
    assert build_knowledge_binding_references({"collections": ["legacy-1"]}) == {
        "database_search.collection_ids": '["legacy-1"]'
    }
