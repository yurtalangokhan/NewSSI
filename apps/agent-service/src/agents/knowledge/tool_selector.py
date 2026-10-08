"""Knowledge tool selector for tools-service retrieval capabilities."""

from __future__ import annotations

import json
from typing import Any

DATABASE_SEARCH = "database_search"
GRAPH_SEARCH = "graph_search"


class KnowledgeToolSelector:
    """Selects retrieval tools based on the keys present in rag_config."""

    @staticmethod
    def select_collections(rag_config: dict) -> dict[str, list[str]]:
        """Return the collection ids each tools-service tool searches.

        - document_processing (or the legacy ``collections`` key) -> database_search
        - knowledge_graph -> graph_search

        Tools without collections are omitted.
        """
        by_tool = {
            DATABASE_SEARCH: rag_config.get("document_processing") or rag_config.get("collections"),
            GRAPH_SEARCH: rag_config.get("knowledge_graph"),
        }
        return {tool: list(ids) for tool, ids in by_tool.items() if ids}

    @classmethod
    def select_tool_names(cls, rag_config: dict) -> list[str]:
        """Return tools-service tool names appropriate for the given rag_config."""
        return list(cls.select_collections(rag_config))

    @staticmethod
    def select_tools(rag_config: dict) -> list[object]:  # noqa: ARG004
        """Compatibility method: agent-service no longer returns local tools."""
        return []


def build_knowledge_binding_references(rag_config: dict[str, Any]) -> dict[str, str]:
    """Return trusted binding references consumed by tools-service knowledge tools."""
    return {
        f"{tool}.collection_ids": json.dumps(collection_ids)
        for tool, collection_ids in KnowledgeToolSelector.select_collections(rag_config).items()
    }
