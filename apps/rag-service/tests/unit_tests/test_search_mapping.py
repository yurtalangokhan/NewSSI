from __future__ import annotations

import pytest

from src.retrieval.contract import (
    GraphEdgeView,
    GraphNodeView,
    RetrievalGraph,
    RetrievalHit,
)
from src.search.mapping import (
    MAX_RELATIONS,
    document_hit_from_retrieval,
    document_search_hits,
    entity_hits_from_graph,
    entity_search_hits,
    file_type_of,
    merge_graphs,
)
from src.search.models import (
    HitKind,
    RelationDirection,
    SearchableCollection,
    SourceType,
)


def _node(
    identifier: str,
    *,
    matched: bool = False,
    score: float | None = None,
    label: str = "Organization",
) -> GraphNodeView:
    return GraphNodeView(
        identifier=identifier,
        name=f"Node {identifier}",
        label=label,
        matched=matched,
        score=score,
        properties={"k": identifier},
    )


def _edge(source: str, target: str, kind: str = "RELATES") -> GraphEdgeView:
    return GraphEdgeView(
        identifier=f"{source}-{kind}-{target}",
        source=source,
        target=target,
        type=kind,
        properties={},
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Policy v3.DOCX", "docx"),
        ("dir/report.final.pdf", "pdf"),
        ("README", None),
        ("", None),
        (None, None),
        (".env", None),
        ("weird.ext-with-dash", None),
        ("long.abcdefghijk", None),
    ],
)
def test_file_type_of(name: str | None, expected: str | None) -> None:
    assert file_type_of(name) == expected


def test_document_hit_reads_source_metadata() -> None:
    hit = RetrievalHit(
        identifier="c1",
        content="passage",
        score=0.2,
        source="vector",
        metadata={
            "source": "Contract.pdf",
            "title": "Supplier contract",
            "page_number": "7",
            "section": "Clause 9",
            "file_id": "f-1",
        },
    )

    document = document_hit_from_retrieval(hit)

    assert document.content == "passage"
    assert (document.source, document.title) == ("Contract.pdf", "Supplier contract")
    assert (document.page, document.section) == (7, "Clause 9")
    assert (document.file_id, document.file_type) == ("f-1", "pdf")
    assert document.metadata["file_id"] == "f-1"


def test_document_hit_falls_back_to_filename_and_ignores_bad_page() -> None:
    hit = RetrievalHit(
        identifier=None,
        content="row",
        score=1.0,
        source="vector",
        metadata={"filename": "sheet.xlsx", "page": "n/a", "file_id": 12},
    )

    document = document_hit_from_retrieval(hit)

    assert (document.source, document.file_type) == ("sheet.xlsx", "xlsx")
    assert document.page is None
    assert document.file_id == "12"
    assert document.title is None


def test_connector_rows_without_source_have_no_file_type() -> None:
    hit = RetrievalHit(
        identifier="r", content="x", score=0, source="vector", metadata={}
    )

    document = document_hit_from_retrieval(hit)

    assert (document.source, document.file_type, document.file_id) == (
        None,
        None,
        None,
    )


def test_entity_hits_are_matched_nodes_by_score_with_relations() -> None:
    graph = RetrievalGraph(
        nodes=(
            _node("a", matched=True, score=0.2),
            _node("b", matched=True, score=0.9, label="Policy"),
            _node("c"),
            _node("d", matched=True),
        ),
        edges=(_edge("b", "a", "GOVERNS"), _edge("c", "b", "OWNS"), _edge("b", "c")),
    )

    hits = entity_hits_from_graph(graph)

    assert [hit.node_id for hit in hits] == ["b", "a", "d"]
    top = hits[0]
    assert top.label == "Policy"
    assert top.neighbor_count == 2
    assert [
        (relation.type, relation.direction, relation.node_id)
        for relation in top.relations
    ] == [
        ("GOVERNS", RelationDirection.OUT, "a"),
        ("RELATES", RelationDirection.OUT, "c"),
        ("OWNS", RelationDirection.IN, "c"),
    ]
    assert top.relations[0].node_name == "Node a"
    assert hits[2].relations == ()
    assert hits[2].neighbor_count == 0


def test_entity_relations_are_capped() -> None:
    edges = tuple(_edge("hub", f"n{index}") for index in range(MAX_RELATIONS + 2))
    nodes = (
        _node("hub", matched=True),
        *(_node(f"n{index}") for index in range(MAX_RELATIONS + 2)),
    )

    (hit,) = entity_hits_from_graph(RetrievalGraph(nodes=nodes, edges=edges))

    assert len(hit.relations) == MAX_RELATIONS
    assert hit.neighbor_count == MAX_RELATIONS + 2


def test_relations_to_unknown_nodes_are_skipped() -> None:
    graph = RetrievalGraph(
        nodes=(_node("a", matched=True),), edges=(_edge("a", "ghost"),)
    )

    (hit,) = entity_hits_from_graph(graph)

    assert hit.relations == ()


def test_merge_graphs_tags_collections_and_deduplicates() -> None:
    first = RetrievalGraph(
        nodes=(_node("a", matched=True), _node("b")),
        edges=(_edge("a", "b"),),
    )
    second = RetrievalGraph(
        nodes=(_node("b", matched=True), _node("c")),
        edges=(_edge("a", "b"), _edge("b", "c")),
    )

    merged = merge_graphs([("col-1", first), ("col-2", second)])

    assert [(node.identifier, node.collection_id) for node in merged.nodes] == [
        ("a", "col-1"),
        ("b", "col-1"),
        ("c", "col-2"),
    ]
    assert merged.nodes[1].matched is True
    assert [edge.identifier for edge in merged.edges] == ["a-RELATES-b", "b-RELATES-c"]
    assert merged.edges[1].collection_id == "col-2"


def test_merge_graphs_caps_keeping_matched_nodes_and_closed_edges() -> None:
    graph = RetrievalGraph(
        nodes=(_node("x"), _node("y"), _node("m", matched=True)),
        edges=(_edge("x", "m"), _edge("y", "m"), _edge("x", "y")),
    )

    merged = merge_graphs([("col", graph)], max_nodes=2, max_edges=5)

    assert [node.identifier for node in merged.nodes] == ["m", "x"]
    assert [edge.identifier for edge in merged.edges] == ["x-RELATES-m"]


def test_merge_graphs_caps_edges() -> None:
    graph = RetrievalGraph(
        nodes=(_node("a"), _node("b")),
        edges=(_edge("a", "b", "ONE"), _edge("a", "b", "TWO")),
    )

    merged = merge_graphs([("col", graph)], max_edges=1)

    assert len(merged.edges) == 1


def test_edges_without_identifier_deduplicate_by_endpoints_and_type() -> None:
    edge = GraphEdgeView(
        identifier=None, source="a", target="b", type="R", properties={}
    )
    graph = RetrievalGraph(nodes=(_node("a"), _node("b")), edges=(edge, edge))

    merged = merge_graphs([("col", graph)])

    assert len(merged.edges) == 1


COLLECTION = SearchableCollection(
    identifier="legal",
    name="Legal",
    source_type=SourceType.DOCUMENT,
    connector_type="",
    sync_status="idle",
    has_graph=True,
)


def test_document_search_hits_keep_vector_hits_in_rank_order() -> None:
    hits = (
        RetrievalHit(
            identifier="c1",
            content="a",
            score=0.2,
            source="vector",
            metadata={"source": "a.pdf"},
        ),
        RetrievalHit(
            identifier="n",
            content="Node",
            score=0.1,
            source="graph",
            metadata={},
        ),
        RetrievalHit(
            identifier=None, content="b", score=0.4, source="vector", metadata={}
        ),
    )

    search_hits = document_search_hits(COLLECTION, hits)

    assert [hit.identifier for hit in search_hits] == ["c1", "legal:2"]
    assert all(hit.kind is HitKind.DOCUMENT for hit in search_hits)
    assert search_hits[0].collection_name == "Legal"
    assert search_hits[0].document is not None
    assert search_hits[0].document.file_type == "pdf"
    assert search_hits[1].score == 0.4


def test_entity_search_hits_carry_node_scores() -> None:
    graph = RetrievalGraph(
        nodes=(_node("a", matched=True, score=0.03), _node("b")),
        edges=(_edge("a", "b"),),
    )

    (hit,) = entity_search_hits(COLLECTION, graph)

    assert (hit.identifier, hit.kind, hit.score) == ("a", HitKind.ENTITY, 0.03)
    assert hit.entity is not None
    assert hit.entity.neighbor_count == 1
    assert hit.collection_id == "legal"
