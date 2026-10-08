"""HTTP adapter of the knowledge search page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.retrieval.adapters import (
    has_graph_search_permission,
    trusted_context_from_request,
)
from src.retrieval.contract import RetrievalKind
from src.search.adapters import (
    CollectionsSearchCatalog,
    GraphStoreNeighborhood,
    RetrievalContractRetriever,
)
from src.search.models import (
    KnowledgeSearchRequest,
    NeighborhoodRequest,
    SearchFilters,
)
from src.search.schemas import (
    KnowledgeSearchRequestBody,
    KnowledgeSearchResponseBody,
    NeighborhoodRequestBody,
    SearchGraphBody,
    SearchSourcesResponseBody,
)
from src.search.service import KnowledgeSearchService
from src.shared.auth import AuthenticatedUser, require_permission

router = APIRouter(tags=["search"])


def get_knowledge_search_service() -> KnowledgeSearchService:
    """Compose the search service from its store adapters."""
    return KnowledgeSearchService(
        catalog=CollectionsSearchCatalog(),
        retriever=RetrievalContractRetriever(),
        neighborhood=GraphStoreNeighborhood(),
    )


KnowledgeSearchServiceDep = Annotated[KnowledgeSearchService, Depends(get_knowledge_search_service)]


def _caller_id(request: Request, user: AuthenticatedUser) -> str:
    """The user a request acts for; internal callers must delegate one."""
    return trusted_context_from_request(request, user).user_id or user.identity


def _optional_set(values: list[str] | None) -> frozenset[str] | None:
    return frozenset(values) if values is not None else None


@router.post("/search", response_model=KnowledgeSearchResponseBody)
async def search_knowledge(
    request: Request,
    body: KnowledgeSearchRequestBody,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
    service: KnowledgeSearchServiceDep,
) -> KnowledgeSearchResponseBody:
    """Search documents and knowledge graphs of every readable collection."""
    user_id = _caller_id(request, user)
    kind = RetrievalKind(body.kind)
    graph_allowed = kind is not RetrievalKind.VECTOR and (await has_graph_search_permission(user_id, user.access_token))
    result = await service.search(
        KnowledgeSearchRequest(
            query=body.query,
            user_id=user_id,
            kind=kind,
            limit=body.limit,
            graph_allowed=graph_allowed,
            filters=SearchFilters(
                collection_ids=_optional_set(body.collection_ids),
                file_types=_optional_set(body.file_types),
                entity_labels=_optional_set(body.entity_labels),
            ),
        )
    )
    return KnowledgeSearchResponseBody.from_result(result)


@router.get("/search/sources", response_model=SearchSourcesResponseBody)
async def list_search_sources(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
    service: KnowledgeSearchServiceDep,
) -> SearchSourcesResponseBody:
    """List the collections the knowledge search page can search."""
    user_id = _caller_id(request, user)
    return SearchSourcesResponseBody.from_sources(await service.list_sources(user_id))


@router.post("/search/graph/neighborhood", response_model=SearchGraphBody)
async def expand_search_neighborhood(
    request: Request,
    body: NeighborhoodRequestBody,
    user: Annotated[AuthenticatedUser, Depends(require_permission("graph:read"))],
    service: KnowledgeSearchServiceDep,
) -> SearchGraphBody:
    """Expand the knowledge graph around result entities."""
    user_id = _caller_id(request, user)
    graph = await service.expand_neighborhood(
        NeighborhoodRequest(
            user_id=user_id,
            collection_id=body.collection_id,
            node_ids=tuple(body.node_ids),
            depth=body.depth,
            limit=body.limit,
        )
    )
    return SearchGraphBody.from_graph(graph)
