"""Run authorized retrieval using vector, graph, and collection adapters."""

from error_contract import GraphSearchPermissionError, TrustedIdentityRequiredError

from src.retrieval.adapters import (
    authorize_collection_read,
    has_graph_search_permission,
    search_collection_graph,
    search_collection_vectors,
)
from src.retrieval.contract import (
    GraphRetrieval,
    RetrievalKind,
    RetrievalRequest,
    RetrievalResult,
    RetrievalService,
    TrustedRetrievalContext,
    VectorDocument,
)
from src.retrieval.schemas import RetrievalRequestBody


async def retrieve_knowledge(
    body: RetrievalRequestBody,
    trusted_context: TrustedRetrievalContext,
    access_token: str | None,
) -> RetrievalResult:
    collection_id = body.collection_id
    user_id = trusted_context.user_id
    if not user_id:
        raise TrustedIdentityRequiredError()
    if RetrievalKind(body.kind) in {RetrievalKind.GRAPH, RetrievalKind.HYBRID} and not (
        await has_graph_search_permission(user_id, access_token)
    ):
        raise GraphSearchPermissionError()

    async def vector_search(query: str, *, limit: int) -> tuple[VectorDocument, ...]:
        return await search_collection_vectors(collection_id, user_id, query, limit=limit)

    async def graph_search(query: str, *, limit: int) -> GraphRetrieval:
        return await search_collection_graph(collection_id, user_id, query, limit=limit)

    service = RetrievalService(
        vector_search=vector_search,
        graph_search=graph_search,
        authorize=authorize_collection_read,
    )
    return await service.retrieve(
        RetrievalRequest(
            query=body.query,
            collection_id=collection_id,
            kind=RetrievalKind(body.kind),
            limit=body.limit,
            trusted_context=trusted_context,
        )
    )
