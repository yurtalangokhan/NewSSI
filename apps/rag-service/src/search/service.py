"""Knowledge search orchestration: scope, bounded fan-out, fusion, facets."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, replace
import time
from typing import TYPE_CHECKING, TypeVar

from error_contract import ForbiddenError, ValidationFailedError

from src.retrieval.contract import MAX_LIMIT as RETRIEVAL_MAX_LIMIT, RetrievalGraph, RetrievalKind
from src.search.facets import apply_filters, count_facets, filter_graph
from src.search.mapping import (
    document_search_hits,
    entity_search_hits,
    merge_graphs,
)
from src.search.models import (
    CollectionOutcome,
    CollectionStatus,
    HitKind,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    NeighborhoodRequest,
    SearchableCollection,
    SearchGraph,
    SearchHit,
)
from src.search.ports import CollectionSearchError
from src.search.ranking import fuse_ranked_lists
from src.shared.observability import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from src.retrieval.contract import RetrievalResult
    from src.search.ports import (
        CollectionCatalog,
        CollectionRetriever,
        GraphNeighborhood,
    )

logger = get_logger(__name__)

DEFAULT_MAX_CONCURRENCY = 8
# A neighbourhood is a connected subgraph; allow this many edges per node.
NEIGHBORHOOD_EDGES_PER_NODE = 2

T = TypeVar("T")


@dataclass(frozen=True)
class _RetrievalTask:
    collection: SearchableCollection
    kind: RetrievalKind


@dataclass(frozen=True)
class _RetrievalOutcome:
    task: _RetrievalTask
    result: RetrievalResult | None


class KnowledgeSearchService:
    """Search every readable collection at once and fuse what comes back."""

    def __init__(
        self,
        *,
        catalog: CollectionCatalog,
        retriever: CollectionRetriever,
        neighborhood: GraphNeighborhood,
        clock: Callable[[], float] = time.perf_counter,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        """Store injected ports; ``max_concurrency`` bounds store fan-out."""
        self._catalog = catalog
        self._retriever = retriever
        self._neighborhood = neighborhood
        self._clock = clock
        self._max_concurrency = max_concurrency

    async def list_sources(self, user_id: str) -> tuple[SearchableCollection, ...]:
        """Collections the user can search, in display order."""
        return await self._catalog.list_searchable(user_id)

    async def search(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResult:
        """Run the fused search; failures of single collections are isolated."""
        started = self._clock()
        query = request.query.strip()
        if not query:
            raise ValidationFailedError(message="Search query must not be empty.")
        if request.kind is RetrievalKind.GRAPH and not request.graph_allowed:
            raise ForbiddenError(message="Graph search permission is required.")

        collections = await self._catalog.list_searchable(request.user_id)
        graph_enabled = request.graph_allowed and request.kind is not RetrievalKind.VECTOR
        tasks = _plan_tasks(collections, request.kind, graph_enabled=graph_enabled)
        per_list_limit = min(request.limit, RETRIEVAL_MAX_LIMIT)
        outcomes = await self._gather_bounded(
            [self._run_task(task, request.user_id, query, per_list_limit) for task in tasks]
        )
        return _assemble_result(
            request,
            collections=collections,
            outcomes=outcomes,
            graph_enabled=graph_enabled,
            elapsed_ms=round((self._clock() - started) * 1000),
        )

    async def expand_neighborhood(self, request: NeighborhoodRequest) -> SearchGraph:
        """Union the ego graphs of the requested nodes as unmatched context."""
        node_ids = tuple(dict.fromkeys(request.node_ids))
        if not node_ids:
            raise ValidationFailedError(message="At least one node id is required.")
        await self._neighborhood.ensure_readable(request.user_id, request.collection_id)
        graphs = await self._gather_bounded(
            [
                self._neighborhood.expand(
                    request.collection_id,
                    node_id,
                    depth=request.depth,
                    limit=request.limit,
                )
                for node_id in node_ids
            ]
        )
        return merge_graphs(
            [(request.collection_id, _unmatched(graph)) for graph in graphs],
            max_nodes=request.limit,
            max_edges=request.limit * NEIGHBORHOOD_EDGES_PER_NODE,
        )

    async def _gather_bounded(self, awaitables: Sequence[Awaitable[T]]) -> list[T]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def bounded(awaitable: Awaitable[T]) -> T:
            async with semaphore:
                return await awaitable

        return list(await asyncio.gather(*(bounded(item) for item in awaitables)))

    async def _run_task(self, task: _RetrievalTask, user_id: str, query: str, limit: int) -> _RetrievalOutcome:
        try:
            result = await self._retriever.retrieve(
                task.collection,
                user_id=user_id,
                query=query,
                kind=task.kind,
                limit=limit,
            )
        except CollectionSearchError:
            logger.warning(
                "Knowledge search failed for collection %s (%s)",
                task.collection.identifier,
                task.kind.value,
                exc_info=True,
            )
            return _RetrievalOutcome(task=task, result=None)
        return _RetrievalOutcome(task=task, result=result)


def _assemble_result(
    request: KnowledgeSearchRequest,
    *,
    collections: Sequence[SearchableCollection],
    outcomes: Sequence[_RetrievalOutcome],
    graph_enabled: bool,
    elapsed_ms: int,
) -> KnowledgeSearchResult:
    """Fuse per-collection outcomes into the ranked, filtered, faceted result."""
    fused = fuse_ranked_lists(
        [_ranked_hits(outcome) for outcome in outcomes],
        key=lambda hit: (hit.kind, hit.collection_id, hit.identifier),
    )
    all_hits = [replace(entry.item, relevance=entry.relevance) for entry in fused]
    filtered = apply_filters(all_hits, request.filters)
    graph = merge_graphs(
        [
            (outcome.task.collection.identifier, outcome.result.graph)
            for outcome in outcomes
            if outcome.result is not None and outcome.result.graph is not None
        ]
    )
    return KnowledgeSearchResult(
        query=request.query.strip(),
        kind=request.kind,
        elapsed_ms=elapsed_ms,
        total=len(filtered),
        graph_available=graph_enabled and any(collection.has_graph for collection in collections),
        graph_unavailable=graph_enabled and any(collection.graph_unreachable for collection in collections),
        hits=tuple(filtered[: request.limit]),
        graph=filter_graph(
            graph,
            request.filters.collection_ids,
            request.filters.entity_labels,
        ),
        collections=_collection_outcomes(outcomes, all_hits),
        facets=count_facets(all_hits),
    )


def _plan_tasks(
    collections: Sequence[SearchableCollection],
    kind: RetrievalKind,
    *,
    graph_enabled: bool,
) -> list[_RetrievalTask]:
    tasks: list[_RetrievalTask] = []
    for collection in collections:
        if kind is not RetrievalKind.GRAPH:
            tasks.append(_RetrievalTask(collection, RetrievalKind.VECTOR))
        if graph_enabled and collection.has_graph:
            tasks.append(_RetrievalTask(collection, RetrievalKind.GRAPH))
    return tasks


def _ranked_hits(outcome: _RetrievalOutcome) -> list[SearchHit]:
    result = outcome.result
    if result is None:
        return []
    if outcome.task.kind is RetrievalKind.GRAPH:
        if result.graph is None:
            return []
        return entity_search_hits(outcome.task.collection, result.graph)
    return document_search_hits(outcome.task.collection, result.hits)


def _collection_outcomes(
    outcomes: Sequence[_RetrievalOutcome], hits: Sequence[SearchHit]
) -> tuple[CollectionOutcome, ...]:
    ordered: dict[str, SearchableCollection] = {}
    failed: set[str] = set()
    for outcome in outcomes:
        identifier = outcome.task.collection.identifier
        ordered.setdefault(identifier, outcome.task.collection)
        if outcome.result is None:
            failed.add(identifier)
    counts = Counter((hit.collection_id, hit.kind) for hit in hits)
    return tuple(
        CollectionOutcome(
            identifier=identifier,
            name=collection.name,
            document_hits=counts[identifier, HitKind.DOCUMENT],
            entity_hits=counts[identifier, HitKind.ENTITY],
            status=CollectionStatus.FAILED if identifier in failed else CollectionStatus.OK,
        )
        for identifier, collection in ordered.items()
    )


def _unmatched(graph: RetrievalGraph) -> RetrievalGraph:
    return RetrievalGraph(
        nodes=tuple(replace(node, matched=False) for node in graph.nodes),
        edges=graph.edges,
    )
