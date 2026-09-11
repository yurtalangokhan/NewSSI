"""Knowledge tool selection for the tools-service ownership model."""

from agents.knowledge.tool_selector import KnowledgeToolSelector


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
