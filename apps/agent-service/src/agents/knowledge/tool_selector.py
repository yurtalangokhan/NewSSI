"""Knowledge tool selector for tools-service retrieval capabilities."""

from __future__ import annotations

import json
from typing import Any


class KnowledgeToolSelector:
    """Selects retrieval tools based on the keys present in rag_config."""

    @staticmethod
    def select_tool_names(rag_config: dict) -> list[str]:
        """Return tools-service tool names appropriate for the given rag_config.

        - document_processing collections -> database_search
        - knowledge_graph collections -> graph_search
        """
        tool_names: list[str] = []
        if rag_config.get("document_processing"):
            tool_names.append("database_search")
        if rag_config.get("knowledge_graph"):
            tool_names.append("graph_search")
        return tool_names

    @staticmethod
    def select_tools(rag_config: dict) -> list[object]:
        """Compatibility method: agent-service no longer returns local tools."""
        return []


def build_knowledge_binding_references(rag_config: dict[str, Any]) -> dict[str, str]:
    """Return trusted binding references consumed by tools-service knowledge tools."""
    references: dict[str, str] = {}
    document_collection_ids = rag_config.get("document_processing") or rag_config.get(
        "collections", []
    )
    graph_collection_ids = rag_config.get("knowledge_graph") or rag_config.get("collections", [])

    if document_collection_ids:
        references["database_search.collection_ids"] = json.dumps(document_collection_ids)
    if graph_collection_ids:
        references["graph_search.collection_ids"] = json.dumps(graph_collection_ids)
    return references
