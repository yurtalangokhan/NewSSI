"""Knowledge retrieval tools backed by rag-service.

Each call returns two things: the text the model reads (``content``) and the
``KnowledgeEvidence`` the chat UI renders (``structured_content``). The
evidence never reaches the model; agent-service strips and persists it.
"""

from __future__ import annotations

import json
from typing import Any

from config_manager import env
from fastmcp.tools.tool import ToolResult
from localization import t

from ..core.base import BaseToolCategory
from ..core.observability import get_logger
from ..core.schema import BoundedCollectionIds, BoundedLimit, ShortText
from ..core.trusted_context import get_current_trusted_context
from ..knowledge.retrieval_client import RagRetrievalClient, RagRetrievalError, RetrievalIdentity
from ..knowledge.search_service import KnowledgeSearchService
from ..knowledge.search_strategies import (
    DocumentSearchStrategy,
    GraphSearchStrategy,
    SearchStrategy,
)
from .response import error_response

logger = get_logger(__name__)

DATABASE_SEARCH = "database_search"
GRAPH_SEARCH = "graph_search"


def _retrieval_url() -> str:
    base_url = (env.INTERNAL_RAG_SERVICE_API_URL or "").rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/api/v1"):
        return f"{base_url}/retrieval"
    return f"{base_url}/api/v1/retrieval"


def build_knowledge_search_service() -> KnowledgeSearchService | None:
    """The configured search service, or ``None`` when rag-service is not set."""
    url = _retrieval_url()
    if not url:
        return None
    return KnowledgeSearchService(
        RagRetrievalClient(retrieval_url=url, internal_token=env.INTERNAL_SERVICE_TOKEN or "")
    )


def _collection_ids_from_binding(tool_name: str) -> list[str]:
    trusted_context = get_current_trusted_context()
    if trusted_context is None:
        return []
    raw = trusted_context.binding_references.get(f"{tool_name}.collection_ids")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",")]
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


def _identity() -> RetrievalIdentity:
    trusted_context = get_current_trusted_context()
    if trusted_context is None:
        return RetrievalIdentity()
    return RetrievalIdentity(user_id=trusted_context.user_id, tenant_id=trusted_context.tenant_id)


def _error(key: str, category: str, default: str | None = None) -> ToolResult:
    return ToolResult(content=error_response(key, default=default, error_category=category))


async def _search(
    *,
    tool: str,
    strategy: SearchStrategy,
    query: str,
    collection_ids: list[str] | None,
    limit: int,
) -> ToolResult:
    collection_ids = collection_ids or _collection_ids_from_binding(tool)
    if not collection_ids:
        return _error("knowledge.collection_required", "validation")
    service = build_knowledge_search_service()
    if service is None:
        return _error("knowledge.rag_service_not_configured", "configuration")
    try:
        outcome = await service.search(
            strategy=strategy,
            tool=tool,
            query=query,
            collection_ids=collection_ids,
            limit=limit,
            identity=_identity(),
        )
    except RagRetrievalError:
        logger.warning("Knowledge retrieval call failed", exc_info=True)
        return _error("knowledge.retrieval_failed", "retrieval", default="Knowledge retrieval failed.")
    return ToolResult(
        content=outcome.model_text,
        structured_content=outcome.evidence.model_dump(mode="json"),
    )


async def database_search_result(query: str, collection_ids: list[str] | None = None, limit: int = 5) -> ToolResult:
    """Retrieve document chunks from rag-service vector search."""
    return await _search(
        tool=DATABASE_SEARCH,
        strategy=DocumentSearchStrategy(),
        query=query,
        collection_ids=collection_ids,
        limit=limit,
    )


async def graph_search_result(query: str, collection_ids: list[str] | None = None, limit: int = 10) -> ToolResult:
    """Retrieve an entity/relationship subgraph from rag-service graph search."""
    return await _search(
        tool=GRAPH_SEARCH,
        strategy=GraphSearchStrategy(),
        query=query,
        collection_ids=collection_ids,
        limit=limit,
    )


class KnowledgeTools(BaseToolCategory):
    """RAG-backed knowledge retrieval tools."""

    @property
    def name(self) -> str:
        return "knowledge_retrieval"

    @property
    def description(self) -> str:
        return t("categories.knowledge_retrieval.description", default="Knowledge retrieval")

    @property
    def label(self) -> str:
        return t("categories.knowledge_retrieval.label", default="Knowledge")

    def register_tools(self, mcp: Any) -> None:
        """Register RAG-backed tools with MCP."""

        @mcp.tool()
        async def database_search(
            query: ShortText,
            collection_ids: BoundedCollectionIds | None = None,
            limit: BoundedLimit = 5,
        ) -> ToolResult:
            """
            Search documents attached to this agent.

            Use this tool for document-level retrieval and factual questions
            over configured knowledge collections. Results are numbered [n].
            """
            return await database_search_result(query, collection_ids, limit)

        @mcp.tool()
        async def document_search(
            query: ShortText,
            collection_ids: BoundedCollectionIds | None = None,
            limit: BoundedLimit = 5,
        ) -> ToolResult:
            """
            Search documents attached to this agent.

            Alias of database_search: same collections, same numbered results.
            """
            return await database_search_result(query, collection_ids, limit)

        @mcp.tool()
        async def graph_search(
            query: ShortText,
            collection_ids: BoundedCollectionIds | None = None,
            limit: BoundedLimit = 10,
        ) -> ToolResult:
            """
            Search the knowledge graph attached to this agent.

            Use this tool for entity relationships, dependencies, and graph
            context over configured knowledge collections.
            """
            return await graph_search_result(query, collection_ids, limit)
