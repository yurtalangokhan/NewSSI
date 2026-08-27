"""Internal agent-facing retrieval HTTP adapter.

Existing document and graph search routes remain the public/UI contract.
This endpoint is additive for tools-service knowledge capabilities.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from langconnect.auth import AuthenticatedUser, require_permission
from langconnect.authorization import get_authorization_client
from langconnect.services.collections import Collection
from langconnect.services.graph_rag_service import GraphRAGService
from langconnect.services.permission_service import get_permission_service
from langconnect.services.retrieval_contract import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    GraphDocument,
    RetrievalHit,
    RetrievalKind,
    RetrievalRequest,
    RetrievalService,
    TrustedRetrievalContext,
    VectorDocument,
)

router = APIRouter(tags=["retrieval"])

INTERNAL_AUTH_HEADER = "x-internal-token"
USER_ID_HEADER = "x-user-id"
TENANT_ID_HEADER = "x-tenant-id"


class RetrievalRequestBody(BaseModel):
    """HTTP body for the agent-facing retrieval contract."""

    model_config = ConfigDict(extra="forbid")

    query: str
    collection_id: str
    kind: Literal["vector", "graph", "hybrid"] = RetrievalKind.VECTOR.value
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class RetrievalHitBody(BaseModel):
    """One retrieval hit in the HTTP response."""

    id: str | None
    content: str
    score: float
    source: str
    metadata: dict[str, object]


class RetrievalResponseBody(BaseModel):
    """HTTP response for the agent-facing retrieval contract."""

    kind: str
    collection_id: str
    hits: list[RetrievalHitBody]
    context: str


def _hit_to_body(hit: RetrievalHit) -> RetrievalHitBody:
    return RetrievalHitBody(
        id=hit.identifier,
        content=hit.content,
        score=hit.score,
        source=hit.source,
        metadata=dict(hit.metadata),
    )


async def _vector_search(
    collection_id: str,
    user_id: str,
    query: str,
    *,
    limit: int,
) -> tuple[VectorDocument, ...]:
    collection = Collection(collection_id=collection_id, user_id=user_id)
    rows = await collection.search(query, limit=limit)
    return tuple(
        VectorDocument(
            identifier=str(row["id"]) if row.get("id") is not None else None,
            content=str(row.get("page_content") or ""),
            score=float(row.get("score") or 0.0),
            metadata=row.get("metadata") or {},
        )
        for row in rows
    )


async def _graph_search(
    collection_id: str,
    user_id: str,
    query: str,
    *,
    limit: int,
) -> tuple[GraphDocument, ...]:
    service = GraphRAGService(collection_id=collection_id, user_id=user_id)
    result = await service.hybrid_search(query, limit=limit)
    if result.nodes:
        return tuple(
            GraphDocument(
                identifier=node.id,
                content=node.name,
                score=result.score,
                context=result.context,
                metadata={"label": node.label, "properties": node.properties},
            )
            for node in result.nodes
        )
    if result.context:
        return (
            GraphDocument(
                identifier=None,
                content=result.context,
                score=result.score,
                context=result.context,
            ),
        )
    return ()


async def _authorize(user_id: str, collection_id: str) -> bool:
    access = await get_permission_service().check_collection_access(
        user_id=user_id,
        collection_id=collection_id,
        required_permission="read",
    )
    return bool(access.get("allowed"))


def _trusted_context_from_request(
    request: Request, authenticated_user: AuthenticatedUser
) -> TrustedRetrievalContext:
    """Build trusted retrieval context from internal transport headers only."""
    internal_token = request.headers.get(INTERNAL_AUTH_HEADER)
    if internal_token and authenticated_user.identity == "internal-service":
        return TrustedRetrievalContext(
            user_id=request.headers.get(USER_ID_HEADER),
            tenant_id=request.headers.get(TENANT_ID_HEADER),
        )
    return TrustedRetrievalContext(user_id=authenticated_user.identity)


async def _has_graph_search_permission(
    user_id: str,
    access_token: str | None,
) -> bool:
    if user_id in ("dev-user", "internal-service"):
        return True
    return await get_authorization_client().has_permission(
        user_id,
        "graph:search",
        access_token,
    )


@router.post("/retrieval", response_model=RetrievalResponseBody)
async def retrieve_knowledge(
    request: Request,
    body: RetrievalRequestBody,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
) -> RetrievalResponseBody:
    """Retrieve vector and/or graph context for an authorized collection."""
    collection_id = body.collection_id
    trusted_context = _trusted_context_from_request(request, user)
    user_id = trusted_context.user_id or user.identity
    if RetrievalKind(body.kind) in {RetrievalKind.GRAPH, RetrievalKind.HYBRID}:
        has_graph_permission = await _has_graph_search_permission(
            user_id,
            user.access_token,
        )
        if not has_graph_permission:
            from error_contract import ForbiddenError

            raise ForbiddenError(message="Graph search permission is required.")

    async def vector_search(query: str, *, limit: int) -> tuple[VectorDocument, ...]:
        return await _vector_search(collection_id, user_id, query, limit=limit)

    async def graph_search(query: str, *, limit: int) -> tuple[GraphDocument, ...]:
        return await _graph_search(collection_id, user_id, query, limit=limit)

    service = RetrievalService(
        vector_search=vector_search,
        graph_search=graph_search,
        authorize=_authorize,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query=body.query,
            collection_id=collection_id,
            kind=RetrievalKind(body.kind),
            limit=body.limit,
            trusted_context=trusted_context,
        )
    )
    return RetrievalResponseBody(
        kind=result.kind.value,
        collection_id=result.collection_id,
        hits=[_hit_to_body(hit) for hit in result.hits],
        context=result.context,
    )
