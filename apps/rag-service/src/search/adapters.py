"""Bind the search ports to collections, the retrieval contract and Neo4j."""

from __future__ import annotations

from typing import TYPE_CHECKING

from error_contract import ApplicationError, ForbiddenError, ValidationFailedError

from src.collections.naming import (
    collection_connector_type,
    collection_display_name,
    collection_sync_status,
)
from src.collections.service import CollectionsManager
from src.documents.service import Collection
from src.graph.connection import GRAPH_STORE_ERRORS
from src.graph.store import GraphStore
from src.retrieval.adapters import (
    graph_view_from_graph_data,
    search_collection_graph,
    search_collection_vectors,
)
from src.retrieval.contract import (
    AuthorizedCollection,
    GraphRetrieval,
    RetrievalGraph,
    RetrievalKind,
    RetrievalRequest,
    RetrievalResult,
    RetrievalService,
    TrustedRetrievalContext,
    VectorDocument,
    redact_graph,
)
from src.search.models import SearchableCollection, SourceType
from src.search.ports import CollectionSearchError
from src.shared.observability import get_logger
from src.shared.vectorstore import VECTOR_STORE_ERRORS

if TYPE_CHECKING:
    from src.collections.schemas import CollectionDetails

logger = get_logger(__name__)

# Failures of a collection's stores (Milvus, the embedder, Neo4j, or a domain
# error), which a search survives; anything else is a bug and must surface.
# ForbiddenError and ValidationFailedError from the retrieval contract are
# excluded at the call site: they mean the request was wrong, not the store.
_COLLECTION_STORE_ERRORS = (
    ApplicationError,
    *VECTOR_STORE_ERRORS,
    *GRAPH_STORE_ERRORS,
)


class CollectionsSearchCatalog:
    """Readable collections, flagged with whether a knowledge graph exists."""

    async def list_searchable(self, user_id: str) -> tuple[SearchableCollection, ...]:
        """Describe every collection the user may read, sorted by name."""
        collections = await CollectionsManager(user_id).list()
        graph_ids = await self._graph_collection_ids()
        sources = [self._describe(collection, graph_ids) for collection in collections]
        return tuple(sorted(sources, key=lambda source: source.name.casefold()))

    @staticmethod
    def _describe(collection: CollectionDetails, graph_ids: frozenset[str] | None) -> SearchableCollection:
        connector_type = collection_connector_type(collection)
        return SearchableCollection(
            identifier=collection["uuid"],
            name=collection_display_name(collection),
            source_type=SourceType.CONNECTOR if connector_type else SourceType.DOCUMENT,
            connector_type=connector_type,
            sync_status=collection_sync_status(collection),
            has_graph=graph_ids is not None and collection["uuid"] in graph_ids,
            graph_unreachable=graph_ids is None,
        )

    @staticmethod
    async def _graph_collection_ids() -> frozenset[str] | None:
        """Ids that have a graph, or ``None`` when the graph store is down."""
        try:
            return frozenset(await GraphStore.list_graph_collection_ids())
        except GRAPH_STORE_ERRORS:
            logger.warning(
                "Neo4j unavailable; searching without knowledge graphs.",
                exc_info=True,
            )
            return None


class RetrievalContractRetriever:
    """Run the retrieval contract for a collection the catalog already vetted."""

    async def retrieve(
        self,
        collection: SearchableCollection,
        *,
        user_id: str,
        query: str,
        kind: RetrievalKind,
        limit: int,
    ) -> RetrievalResult:
        """Return redacted, bounded retrieval output for one collection."""
        vetted = AuthorizedCollection(identifier=collection.identifier, name=collection.name)

        async def vector_search(search_query: str, *, limit: int) -> tuple[VectorDocument, ...]:
            return await search_collection_vectors(collection.identifier, user_id, search_query, limit=limit)

        async def graph_search(search_query: str, *, limit: int) -> GraphRetrieval:
            return await search_collection_graph(collection.identifier, user_id, search_query, limit=limit)

        service = RetrievalService(vector_search=vector_search, graph_search=graph_search)
        try:
            return await service.retrieve_authorized(
                RetrievalRequest(
                    query=query,
                    collection_id=collection.identifier,
                    kind=kind,
                    limit=limit,
                    trusted_context=TrustedRetrievalContext(user_id=user_id),
                ),
                vetted,
            )
        except (ForbiddenError, ValidationFailedError):
            raise
        except _COLLECTION_STORE_ERRORS as exc:
            raise CollectionSearchError(f"{kind.value} search failed for collection {collection.identifier}") from exc


class GraphStoreNeighborhood:
    """Ego graphs around nodes, read from Neo4j after a collection read check."""

    async def ensure_readable(self, user_id: str, collection_id: str) -> None:
        """Raise ``NotFoundError`` unless the user may read the collection."""
        await Collection(collection_id, user_id).ensure_exists("read")

    async def expand(self, collection_id: str, node_id: str, *, depth: int, limit: int) -> RetrievalGraph:
        """Return the redacted ego graph of ``node_id``."""
        data = await GraphStore(collection_id).get_neighborhood(node_id=node_id, depth=depth, limit=limit)
        return redact_graph(graph_view_from_graph_data(data))
