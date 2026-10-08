from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

import pytest
from error_contract import ForbiddenError, NotFoundError, ValidationFailedError

from src.retrieval.contract import (
    GraphEdgeView,
    GraphNodeView,
    RetrievalGraph,
    RetrievalHit,
    RetrievalKind,
    RetrievalResult,
)
from src.search import schemas
from src.search.models import (
    DEFAULT_NEIGHBORHOOD_DEPTH,
    CollectionStatus,
    FacetValue,
    HitKind,
    KnowledgeSearchRequest,
    NeighborhoodRequest,
    SearchableCollection,
    SearchFilters,
    SourceType,
)
from src.search.ports import CollectionSearchError
from src.search.schemas import NeighborhoodRequestBody
from src.search.service import KnowledgeSearchService

LEGAL = SearchableCollection(
    identifier="legal",
    name="Legal",
    source_type=SourceType.DOCUMENT,
    connector_type="",
    sync_status="idle",
    has_graph=True,
)
DRIVE = SearchableCollection(
    identifier="drive",
    name="Drive",
    source_type=SourceType.CONNECTOR,
    connector_type="google-drive",
    sync_status="succeeded",
    has_graph=False,
)


def _vector_hit(identifier: str | None, source: str) -> RetrievalHit:
    return RetrievalHit(
        identifier=identifier,
        content=f"text {identifier}",
        score=0.3,
        source="vector",
        metadata={"source": source, "file_id": f"f-{identifier}"},
    )


def _node(identifier: str, *, matched: bool, label: str = "Policy") -> GraphNodeView:
    return GraphNodeView(
        identifier=identifier,
        name=identifier.upper(),
        label=label,
        matched=matched,
        score=0.02 if matched else None,
        properties={},
    )


LEGAL_GRAPH = RetrievalGraph(
    nodes=(_node("p", matched=True), _node("q", matched=False, label="Role")),
    edges=(
        GraphEdgeView(
            identifier="pq", source="p", target="q", type="OWNS", properties={}
        ),
    ),
)


def _result(
    collection: SearchableCollection,
    kind: RetrievalKind,
    hits: tuple[RetrievalHit, ...] = (),
    graph: RetrievalGraph | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        kind=kind,
        collection_id=collection.identifier,
        hits=hits,
        context="",
        collection_name=collection.name,
        graph=graph,
    )


@dataclass
class FakeCatalog:
    collections: tuple[SearchableCollection, ...] = (LEGAL, DRIVE)
    calls: list[str] = field(default_factory=list)

    async def list_searchable(self, user_id: str) -> tuple[SearchableCollection, ...]:
        """Record the caller and return the configured collections."""
        self.calls.append(user_id)
        return self.collections


@dataclass
class FakeRetriever:
    failing: set[tuple[str, RetrievalKind]] = field(default_factory=set)
    calls: list[tuple[str, RetrievalKind, int, str]] = field(default_factory=list)
    active: int = 0
    peak: int = 0

    async def retrieve(
        self,
        collection: SearchableCollection,
        *,
        user_id: str,
        query: str,
        kind: RetrievalKind,
        limit: int,
    ) -> RetrievalResult:
        """Record the call and answer from fixed fixtures."""
        self.calls.append((collection.identifier, kind, limit, user_id))
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        if (collection.identifier, kind) in self.failing:
            raise CollectionSearchError("store down")
        if kind is RetrievalKind.GRAPH:
            return _result(collection, kind, graph=LEGAL_GRAPH)
        if collection is LEGAL:
            hits = (_vector_hit("l1", "a.pdf"), _vector_hit("l2", "b.docx"))
        else:
            hits = (_vector_hit(None, "sheet.xlsx"),)
        return _result(collection, kind, hits=hits)


@dataclass
class FakeNeighborhood:
    readable: bool = True
    graphs: dict[str, RetrievalGraph] = field(default_factory=dict)
    calls: list[tuple[str, str, int, int]] = field(default_factory=list)

    async def ensure_readable(self, user_id: str, collection_id: str) -> None:
        """Deny access unless configured readable."""
        if not self.readable:
            raise NotFoundError(message="Collection not found")

    async def expand(
        self, collection_id: str, node_id: str, *, depth: int, limit: int
    ) -> RetrievalGraph:
        """Record the call and return the configured ego graph."""
        self.calls.append((collection_id, node_id, depth, limit))
        return self.graphs[node_id]


class FakeClock:
    def __init__(self) -> None:
        """Yield a start and an end reading 250 ms apart."""
        self.values = iter([10.0, 10.25])

    def __call__(self) -> float:
        """Return the next reading."""
        return next(self.values)


def _service(
    catalog: FakeCatalog | None = None,
    retriever: FakeRetriever | None = None,
    neighborhood: FakeNeighborhood | None = None,
    max_concurrency: int = 8,
) -> KnowledgeSearchService:
    return KnowledgeSearchService(
        catalog=catalog or FakeCatalog(),
        retriever=retriever or FakeRetriever(),
        neighborhood=neighborhood or FakeNeighborhood(),
        clock=FakeClock(),
        max_concurrency=max_concurrency,
    )


def _request(**overrides: object) -> KnowledgeSearchRequest:
    values: dict[str, object] = {
        "query": " retention ",
        "user_id": "user-1",
        "graph_allowed": True,
    }
    values.update(overrides)
    return KnowledgeSearchRequest(**values)  # type: ignore[arg-type]


async def test_hybrid_search_fuses_documents_and_entities() -> None:
    retriever = FakeRetriever()

    result = await _service(retriever=retriever).search(_request(limit=10))

    assert result.query == "retention"
    assert result.kind is RetrievalKind.HYBRID
    assert result.elapsed_ms == 250
    assert result.graph_available is True
    assert sorted(retriever.calls) == [
        ("drive", RetrievalKind.VECTOR, 10, "user-1"),
        ("legal", RetrievalKind.GRAPH, 10, "user-1"),
        ("legal", RetrievalKind.VECTOR, 10, "user-1"),
    ]
    assert [(hit.kind, hit.identifier) for hit in result.hits] == [
        (HitKind.DOCUMENT, "l1"),
        (HitKind.ENTITY, "p"),
        (HitKind.DOCUMENT, "drive:0"),
        (HitKind.DOCUMENT, "l2"),
    ]
    first, entity = result.hits[0], result.hits[1]
    assert first.relevance == 1.0
    assert first.score == 0.3
    assert (first.collection_id, first.collection_name) == ("legal", "Legal")
    assert first.document is not None
    assert first.document.file_type == "pdf"
    assert entity.entity is not None
    assert entity.entity.relations[0].node_name == "Q"
    assert result.hits[3].relevance < result.hits[0].relevance
    assert result.total == 4
    assert [node.identifier for node in result.graph.nodes] == ["p", "q"]
    assert result.graph.nodes[0].collection_id == "legal"
    assert result.facets.file_types == (
        FacetValue("docx", 1),
        FacetValue("pdf", 1),
        FacetValue("xlsx", 1),
    )
    assert result.facets.entity_labels == (FacetValue("Policy", 1),)
    assert [
        (item.identifier, item.document_hits, item.entity_hits, item.status)
        for item in result.collections
    ] == [
        ("legal", 2, 1, CollectionStatus.OK),
        ("drive", 1, 0, CollectionStatus.OK),
    ]


async def test_vector_search_skips_graph_retrieval() -> None:
    retriever = FakeRetriever()

    result = await _service(retriever=retriever).search(
        _request(kind=RetrievalKind.VECTOR)
    )

    assert {kind for _, kind, _, _ in retriever.calls} == {RetrievalKind.VECTOR}
    assert result.graph.nodes == ()
    assert result.graph_available is False
    assert all(hit.kind is HitKind.DOCUMENT for hit in result.hits)


async def test_graph_search_only_queries_graph_collections() -> None:
    retriever = FakeRetriever()

    result = await _service(retriever=retriever).search(
        _request(kind=RetrievalKind.GRAPH)
    )

    assert retriever.calls == [("legal", RetrievalKind.GRAPH, 50, "user-1")]
    assert [hit.identifier for hit in result.hits] == ["p"]
    assert [item.identifier for item in result.collections] == ["legal"]


async def test_graph_kind_requires_graph_permission() -> None:
    with pytest.raises(ForbiddenError):
        await _service().search(_request(kind=RetrievalKind.GRAPH, graph_allowed=False))


async def test_hybrid_without_graph_permission_degrades_to_vector() -> None:
    retriever = FakeRetriever()

    result = await _service(retriever=retriever).search(_request(graph_allowed=False))

    assert {kind for _, kind, _, _ in retriever.calls} == {RetrievalKind.VECTOR}
    assert result.graph_available is False


async def test_blank_query_is_rejected() -> None:
    with pytest.raises(ValidationFailedError):
        await _service().search(_request(query="   "))


async def test_failing_collection_is_isolated_and_reported() -> None:
    retriever = FakeRetriever(failing={("legal", RetrievalKind.VECTOR)})

    result = await _service(retriever=retriever).search(_request())

    assert [hit.identifier for hit in result.hits] == ["p", "drive:0"]
    assert result.collections[0].status is CollectionStatus.FAILED
    assert result.collections[0].entity_hits == 1
    assert result.collections[1].status is CollectionStatus.OK


async def test_programming_errors_are_not_reported_as_failed_collections() -> None:
    class Buggy(FakeRetriever):
        async def retrieve(self, *args: object, **kwargs: object) -> RetrievalResult:
            raise TypeError("bug")

    with pytest.raises(TypeError):
        await _service(retriever=Buggy()).search(_request())


async def test_graph_store_outage_is_reported_when_graph_was_wanted() -> None:
    unreachable = replace(LEGAL, has_graph=False, graph_unreachable=True)
    catalog = FakeCatalog(collections=(unreachable,))

    result = await _service(catalog=catalog).search(_request())

    assert result.graph_available is False
    assert result.graph_unavailable is True


async def test_graph_store_outage_is_not_reported_for_vector_searches() -> None:
    unreachable = replace(LEGAL, has_graph=False, graph_unreachable=True)
    catalog = FakeCatalog(collections=(unreachable,))

    result = await _service(catalog=catalog).search(_request(kind=RetrievalKind.VECTOR))

    assert result.graph_unavailable is False


async def test_graph_is_reachable_by_default() -> None:
    result = await _service().search(_request())

    assert result.graph_unavailable is False


def test_graph_permission_must_be_stated_explicitly() -> None:
    with pytest.raises(TypeError):
        KnowledgeSearchRequest(query="q", user_id="user-1")  # type: ignore[call-arg]


async def test_filters_refine_hits_but_not_facets_or_counts() -> None:
    result = await _service().search(
        _request(
            filters=SearchFilters(
                collection_ids=frozenset({"legal"}),
                file_types=frozenset({"pdf"}),
            )
        )
    )

    # A file type asks for documents: the entity "p" is filtered out.
    assert [hit.identifier for hit in result.hits] == ["l1"]
    assert result.total == 1
    assert len(result.facets.file_types) == 3
    assert result.collections[1].document_hits == 1


async def test_collection_filter_restricts_graph() -> None:
    result = await _service().search(
        _request(filters=SearchFilters(collection_ids=frozenset({"drive"})))
    )

    assert result.graph.nodes == ()


async def test_entity_label_filter_restricts_graph_and_hits() -> None:
    result = await _service().search(
        _request(filters=SearchFilters(entity_labels=frozenset({"role"})))
    )

    assert [node.identifier for node in result.graph.nodes] == ["q"]
    assert all(hit.entity is not None for hit in result.hits)


async def test_limit_truncates_hits_but_total_counts_all() -> None:
    result = await _service().search(_request(limit=2))

    assert len(result.hits) == 2
    assert result.total == 4


async def test_per_collection_limit_is_bounded_by_retrieval_contract() -> None:
    retriever = FakeRetriever()

    await _service(retriever=retriever).search(
        _request(limit=100, kind=RetrievalKind.VECTOR)
    )

    assert {limit for _, _, limit, _ in retriever.calls} == {50}


async def test_fan_out_concurrency_is_bounded() -> None:
    many = tuple(
        SearchableCollection(
            identifier=f"c{index}",
            name=f"C{index}",
            source_type=SourceType.DOCUMENT,
            connector_type="",
            sync_status="idle",
            has_graph=False,
        )
        for index in range(6)
    )
    retriever = FakeRetriever()

    await _service(
        catalog=FakeCatalog(collections=many),
        retriever=retriever,
        max_concurrency=2,
    ).search(_request(kind=RetrievalKind.VECTOR))

    assert len(retriever.calls) == 6
    assert retriever.peak == 2


async def test_no_readable_collections_returns_empty_result() -> None:
    result = await _service(catalog=FakeCatalog(collections=())).search(_request())

    assert result.hits == ()
    assert result.total == 0
    assert result.collections == ()
    assert result.graph_available is False


async def test_list_sources_delegates_to_catalog() -> None:
    catalog = FakeCatalog()

    sources = await _service(catalog=catalog).list_sources("user-9")

    assert sources == (LEGAL, DRIVE)
    assert catalog.calls == ["user-9"]


async def test_neighborhood_merges_expansions_as_unmatched() -> None:
    neighborhood = FakeNeighborhood(
        graphs={
            "p": RetrievalGraph(
                nodes=(_node("p", matched=True), _node("q", matched=False)),
                edges=LEGAL_GRAPH.edges,
            ),
            "q": RetrievalGraph(
                nodes=(_node("q", matched=False), _node("r", matched=False)),
                edges=(
                    GraphEdgeView(
                        identifier="qr",
                        source="q",
                        target="r",
                        type="HAS",
                        properties={},
                    ),
                ),
            ),
        }
    )

    graph = await _service(neighborhood=neighborhood).expand_neighborhood(
        NeighborhoodRequest(
            user_id="user-1",
            collection_id="legal",
            node_ids=("p", "q", "p"),
            depth=2,
            limit=30,
        )
    )

    assert sorted(neighborhood.calls) == [
        ("legal", "p", 2, 30),
        ("legal", "q", 2, 30),
    ]
    assert [node.identifier for node in graph.nodes] == ["p", "q", "r"]
    assert not any(node.matched for node in graph.nodes)
    assert [edge.identifier for edge in graph.edges] == ["pq", "qr"]
    assert {node.collection_id for node in graph.nodes} == {"legal"}


async def test_neighborhood_is_capped_by_limit() -> None:
    neighborhood = FakeNeighborhood(
        graphs={
            "p": RetrievalGraph(
                nodes=(_node("p", matched=False), _node("q", matched=False)),
                edges=LEGAL_GRAPH.edges,
            )
        }
    )

    graph = await _service(neighborhood=neighborhood).expand_neighborhood(
        NeighborhoodRequest(
            user_id="u", collection_id="legal", node_ids=("p",), limit=1
        )
    )

    assert [node.identifier for node in graph.nodes] == ["p"]
    assert graph.edges == ()


async def test_neighborhood_requires_collection_access() -> None:
    neighborhood = FakeNeighborhood(readable=False)

    with pytest.raises(NotFoundError):
        await _service(neighborhood=neighborhood).expand_neighborhood(
            NeighborhoodRequest(user_id="u", collection_id="x", node_ids=("p",))
        )
    assert neighborhood.calls == []


async def test_neighborhood_requires_node_ids() -> None:
    with pytest.raises(ValidationFailedError):
        await _service().expand_neighborhood(
            NeighborhoodRequest(user_id="u", collection_id="x", node_ids=())
        )


def test_neighborhood_request_defaults_match_the_http_defaults() -> None:
    request = NeighborhoodRequest(user_id="u", collection_id="c", node_ids=("n",))

    assert request.depth == DEFAULT_NEIGHBORHOOD_DEPTH
    assert request.limit == schemas.DEFAULT_NEIGHBORHOOD_LIMIT
    assert (
        NeighborhoodRequestBody(collection_id="c", node_ids=["n"]).limit
        == request.limit
    )
