from __future__ import annotations

from src.search.facets import apply_filters, count_facets, filter_graph
from src.search.models import (
    DocumentHit,
    EntityHit,
    FacetValue,
    HitKind,
    SearchFilters,
    SearchGraph,
    SearchGraphEdge,
    SearchGraphNode,
    SearchHit,
)


def _document(identifier: str, collection: str, file_type: str | None) -> SearchHit:
    return SearchHit(
        identifier=identifier,
        kind=HitKind.DOCUMENT,
        relevance=1.0,
        score=0.1,
        collection_id=collection,
        collection_name=collection,
        document=DocumentHit(
            content="c",
            file_id=None,
            source=None,
            title=None,
            page=None,
            section=None,
            file_type=file_type,
            metadata={},
        ),
    )


def _entity(identifier: str, collection: str, label: str) -> SearchHit:
    return SearchHit(
        identifier=identifier,
        kind=HitKind.ENTITY,
        relevance=1.0,
        score=0.1,
        collection_id=collection,
        collection_name=collection,
        entity=EntityHit(
            node_id=identifier,
            name=identifier,
            label=label,
            matched=True,
            properties={},
            relations=(),
            neighbor_count=0,
        ),
    )


HITS = (
    _document("d1", "legal", "pdf"),
    _entity("e1", "kg", "Policy"),
    _document("d2", "policy", "docx"),
    _document("d3", "legal", "pdf"),
    _entity("e2", "kg", "Organization"),
    _document("d4", "drive", None),
    _entity("e3", "kg", "Policy"),
)


def _ids(hits: list[SearchHit]) -> list[str]:
    return [hit.identifier for hit in hits]


def test_facets_count_by_frequency_then_value() -> None:
    facets = count_facets(HITS)

    assert facets.file_types == (FacetValue("pdf", 2), FacetValue("docx", 1))
    assert facets.entity_labels == (
        FacetValue("Policy", 2),
        FacetValue("Organization", 1),
    )


def test_no_filters_keep_every_hit() -> None:
    assert _ids(apply_filters(HITS, SearchFilters())) == _ids(list(HITS))


def test_collection_filter_applies_to_both_kinds() -> None:
    filters = SearchFilters(collection_ids=frozenset({"legal", "kg"}))

    assert _ids(apply_filters(HITS, filters)) == ["d1", "e1", "d3", "e2", "e3"]


def test_file_type_filter_keeps_only_matching_documents() -> None:
    filters = SearchFilters(file_types=frozenset({"PDF"}))

    assert _ids(apply_filters(HITS, filters)) == ["d1", "d3"]


def test_entity_label_filter_keeps_only_matching_entities_case_insensitively() -> None:
    filters = SearchFilters(entity_labels=frozenset({"policy"}))

    assert _ids(apply_filters(HITS, filters)) == ["e1", "e3"]


def test_both_kind_filters_keep_the_matches_of_each_kind() -> None:
    filters = SearchFilters(
        file_types=frozenset({"docx"}), entity_labels=frozenset({"Policy"})
    )

    assert _ids(apply_filters(HITS, filters)) == ["e1", "d2", "e3"]


def test_filters_combine() -> None:
    filters = SearchFilters(
        collection_ids=frozenset({"legal", "kg"}),
        file_types=frozenset({"pdf"}),
        entity_labels=frozenset({"Organization"}),
    )

    assert _ids(apply_filters(HITS, filters)) == ["d1", "d3", "e2"]


def _graph() -> SearchGraph:
    def node(identifier: str, collection: str, label: str = "L") -> SearchGraphNode:
        return SearchGraphNode(
            identifier=identifier,
            name=identifier,
            label=label,
            matched=False,
            score=None,
            collection_id=collection,
            properties={},
        )

    return SearchGraph(
        nodes=(node("a", "kg", "Agent"), node("b", "kg"), node("c", "other")),
        edges=(
            SearchGraphEdge(
                identifier="ab",
                source="a",
                target="b",
                type="R",
                collection_id="kg",
                properties={},
            ),
            SearchGraphEdge(
                identifier="bc",
                source="b",
                target="c",
                type="R",
                collection_id="other",
                properties={},
            ),
        ),
    )


def test_graph_filter_keeps_selected_collections_closed() -> None:
    graph = filter_graph(_graph(), frozenset({"kg"}), None)

    assert [node.identifier for node in graph.nodes] == ["a", "b"]
    assert [edge.identifier for edge in graph.edges] == ["ab"]


def test_graph_without_collection_filter_is_unchanged() -> None:
    graph = _graph()

    assert filter_graph(graph, None, None) is graph


def test_graph_filter_keeps_only_selected_entity_labels() -> None:
    graph = filter_graph(_graph(), None, frozenset({"agent", "l"}))

    assert [node.identifier for node in graph.nodes] == ["a", "b", "c"]
    graph = filter_graph(_graph(), None, frozenset({"AGENT"}))

    assert [node.identifier for node in graph.nodes] == ["a"]
    assert graph.edges == ()
