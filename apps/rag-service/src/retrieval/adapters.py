"""Per-collection retrieval adapters shared by the retrieval and search domains.

Each adapter binds one retrieval port to a concrete store (Milvus through
``Collection``, Neo4j through ``GraphRAGService``) or to the collection and
permission checks, so contract code stays free of infrastructure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from error_contract import ForbiddenError

from src.collections.service import CollectionsManager
from src.documents.service import Collection
from src.graph.service import GraphRAGService
from src.retrieval.contract import (
    AuthorizedCollection,
    GraphEdgeView,
    GraphNodeView,
    GraphRetrieval,
    RetrievalGraph,
    TrustedRetrievalContext,
    VectorDocument,
)
from src.shared.authorization import get_authorization_client

if TYPE_CHECKING:
    from collections.abc import Iterable

    from starlette.requests import HTTPConnection

    from src.graph.schemas import GraphData, GraphSearchResult
    from src.shared.auth import AuthenticatedUser

USER_ID_HEADER = "x-user-id"
TENANT_ID_HEADER = "x-tenant-id"
INTERNAL_SERVICE_IDENTITY = "internal-service"
_RESERVED_DELEGATED_IDENTITIES = frozenset({INTERNAL_SERVICE_IDENTITY, "dev-user"})


def graph_view_from_graph_data(data: GraphData | GraphSearchResult, seed_ids: Iterable[str] = ()) -> RetrievalGraph:
    """Map graph-domain nodes and edges onto the retrieval port's value types.

    Nodes named in ``seed_ids`` are marked as direct query matches; properties
    are passed through unredacted, so callers redact before exposing them.
    """
    seeds = frozenset(seed_ids)
    return RetrievalGraph(
        nodes=tuple(
            GraphNodeView(
                identifier=node.id,
                name=node.name,
                label=node.label,
                matched=node.id in seeds,
                score=_rrf_score(node.properties),
                properties=node.properties,
            )
            for node in data.nodes
        ),
        edges=tuple(
            GraphEdgeView(
                identifier=edge.id,
                source=edge.source,
                target=edge.target,
                type=edge.type,
                properties=edge.properties,
            )
            for edge in data.edges
        ),
    )


def graph_retrieval_from_search_result(result: GraphSearchResult) -> GraphRetrieval:
    """Map graph-domain search output onto the retrieval port's value type."""
    graph = graph_view_from_graph_data(result, result.seed_node_ids)
    return GraphRetrieval(
        nodes=graph.nodes,
        edges=graph.edges,
        context=result.context,
        score=result.score,
    )


def _rrf_score(properties: dict[str, object]) -> float | None:
    score = properties.get("rrf_score")
    return float(score) if isinstance(score, int | float) else None


def _chunk_identifier(row: dict[str, object]) -> str | None:
    """A hit's own chunk id; the file id would merge every chunk of a file."""
    identifier = row.get("chunk_id") or row.get("id")
    return str(identifier) if identifier is not None else None


async def search_collection_vectors(
    collection_id: str,
    user_id: str,
    query: str,
    *,
    limit: int,
) -> tuple[VectorDocument, ...]:
    """Run a vector similarity search against one collection."""
    collection = Collection(collection_id=collection_id, user_id=user_id)
    rows = await collection.search(query, limit=limit)
    return tuple(
        VectorDocument(
            identifier=_chunk_identifier(row),
            content=str(row.get("page_content") or ""),
            score=float(row.get("score") or 0.0),
            metadata=row.get("metadata") or {},
        )
        for row in rows
    )


async def search_collection_graph(
    collection_id: str,
    user_id: str,
    query: str,
    *,
    limit: int,
) -> GraphRetrieval:
    """Run the hybrid graph search against one collection's knowledge graph."""
    service = GraphRAGService(collection_id=collection_id, user_id=user_id)
    result = await service.hybrid_search(query, limit=limit)
    return graph_retrieval_from_search_result(result)


async def authorize_collection_read(user_id: str, collection_id: str) -> AuthorizedCollection | None:
    """Return the collection when the user may read it, else ``None``."""
    details = await CollectionsManager(user_id).get(collection_id)
    if details is None:
        return None
    return AuthorizedCollection(identifier=collection_id, name=details.get("name"))


def trusted_context_from_request(
    request: HTTPConnection, authenticated_user: AuthenticatedUser
) -> TrustedRetrievalContext:
    """Require user delegation for an already-authenticated internal caller."""
    if authenticated_user.identity == INTERNAL_SERVICE_IDENTITY:
        user_id = (request.headers.get(USER_ID_HEADER) or "").strip()
        if not user_id or user_id in _RESERVED_DELEGATED_IDENTITIES:
            raise ForbiddenError(message="A delegated user identity is required.")
        return TrustedRetrievalContext(
            user_id=user_id,
            tenant_id=request.headers.get(TENANT_ID_HEADER),
        )
    return TrustedRetrievalContext(user_id=authenticated_user.identity)


async def has_graph_search_permission(
    user_id: str,
    access_token: str | None,
) -> bool:
    """Whether the user may run graph searches (internal callers always may)."""
    if user_id == INTERNAL_SERVICE_IDENTITY:
        return True
    return await get_authorization_client().has_permission(
        user_id,
        "graph:search",
        access_token,
    )
