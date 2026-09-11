"""Knowledge retrieval tools backed by rag-service."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from i18n import t

from ..core.base import BaseToolCategory
from ..core.settings import get_settings
from ..core.trusted_context import get_current_trusted_context
from .response import error_response


def _retrieval_url() -> str:
    base_url = get_settings().rag_service_api_url.rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/api/v1"):
        return f"{base_url}/retrieval"
    return f"{base_url}/api/v1/retrieval"


def _trusted_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.internal_service_token:
        headers["x-internal-token"] = settings.internal_service_token

    trusted_context = get_current_trusted_context()
    if trusted_context and trusted_context.user_id:
        headers["x-user-id"] = trusted_context.user_id
    if trusted_context and trusted_context.tenant_id:
        headers["x-tenant-id"] = trusted_context.tenant_id
    return headers


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


def _retrieve(
    query: str,
    collection_ids: list[str] | None,
    *,
    tool_name: Literal["database_search", "graph_search"],
    kind: Literal["vector", "graph", "hybrid"],
    limit: int = 5,
) -> str:
    collection_ids = collection_ids or _collection_ids_from_binding(tool_name)
    if not collection_ids:
        return error_response(
            "knowledge.collection_required",
            error_category="validation",
        )
    url = _retrieval_url()
    if not url:
        return error_response(
            "knowledge.rag_service_not_configured",
            error_category="configuration",
        )

    contexts: list[str] = []
    for collection_id in collection_ids:
        payload = {
            "query": query,
            "collection_id": collection_id,
            "kind": kind,
            "limit": limit,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=_trusted_headers())
            response.raise_for_status()
            context = str(response.json().get("context") or "").strip()
            if context:
                contexts.append(context)
        except Exception as exc:
            return json.dumps(
                {
                    "success": False,
                    "error": str(exc),
                    "error_category": "retrieval",
                }
            )

    if not contexts:
        return "No relevant information found in the configured knowledge collections."
    return "\n\n".join(contexts)


def database_search_results(
    query: str, collection_ids: list[str] | None = None, limit: int = 5
) -> str:
    """Retrieve document context from rag-service vector search."""
    return _retrieve(
        query,
        collection_ids,
        tool_name="database_search",
        kind="vector",
        limit=limit,
    )


def graph_search_results(
    query: str, collection_ids: list[str] | None = None, limit: int = 10
) -> str:
    """Retrieve graph context from rag-service graph search."""
    return _retrieve(
        query,
        collection_ids,
        tool_name="graph_search",
        kind="graph",
        limit=limit,
    )


class KnowledgeTools(BaseToolCategory):
    """RAG-backed knowledge retrieval tools."""

    @property
    def name(self) -> str:
        return "knowledge_retrieval"

    @property
    def description(self) -> str:
        return t("categories.knowledge.description", default="Knowledge retrieval")

    @property
    def label(self) -> str:
        return t("categories.knowledge.label", default="Knowledge")

    def register_tools(self, mcp: Any) -> None:
        """Register RAG-backed tools with MCP."""

        @mcp.tool()
        def database_search(
            query: str, collection_ids: list[str] | None = None, limit: int = 5
        ) -> str:
            """
            Search documents attached to this agent.

            Use this tool for document-level retrieval and factual questions
            over configured knowledge collections.
            """
            return database_search_results(query, collection_ids, limit)

        @mcp.tool()
        def graph_search(
            query: str, collection_ids: list[str] | None = None, limit: int = 10
        ) -> str:
            """
            Search the knowledge graph attached to this agent.

            Use this tool for entity relationships, dependencies, and graph
            context over configured knowledge collections.
            """
            return graph_search_results(query, collection_ids, limit)
