"""Evidence built from flow retrieval node results."""

from __future__ import annotations

from schemas.knowledge_evidence import EvidenceKind

from integrations.rag_client import RagChunk
from service.knowledge_evidence.flow_evidence import (
    document_evidence,
    graph_evidence,
    tool_name_for_node,
)


def test_tool_name_for_node_maps_retrieval_node_types() -> None:
    assert tool_name_for_node("DocumentSearch") == "document_search"
    assert tool_name_for_node("KnowledgeBase") == "document_search"
    assert tool_name_for_node("GraphSearch") == "graph_search"
    assert tool_name_for_node("GraphEntitySearch") == "graph_entity_search"
    assert tool_name_for_node("GraphNeighborhood") == "graph_neighborhood"


def test_document_evidence_numbers_chunks_and_keeps_their_sources() -> None:
    chunks = [
        RagChunk(text="first", score=0.9, metadata={"source": "a.pdf", "page": 2}, id="chk-1"),
        RagChunk(text="", score=0.5),
        RagChunk(text="second", score=0.8, metadata={"title": "Guide"}),
    ]

    evidence = document_evidence(
        tool="document_search",
        query="leave",
        collection_id="col-1",
        chunks=chunks,
        model_context="first\n\nsecond",
        elapsed_ms=12,
    )

    assert evidence.kind is EvidenceKind.DOCUMENT
    assert [(c.ref, c.id, c.content) for c in evidence.chunks] == [(1, "chk-1", "first"), (2, None, "second")]
    assert evidence.chunks[0].source.document == "a.pdf"
    assert evidence.chunks[0].source.page == 2
    assert evidence.chunks[1].source.title == "Guide"
    assert [c.id for c in evidence.collections] == ["col-1"]
    assert evidence.model_context == "first\n\nsecond"
    assert evidence.elapsed_ms == 12


def test_graph_evidence_marks_seed_nodes_from_a_search_result() -> None:
    payload = {
        "nodes": [
            {"id": "a", "name": "Carry-over", "label": "Process", "properties": {"rrf_score": 0.0098}},
            {"id": "b", "name": "Line Manager", "label": "Role", "properties": {}},
        ],
        "edges": [{"id": "e", "source": "a", "target": "b", "type": "REQUIRES_APPROVAL_FROM"}],
        "context": "== Knowledge Graph Context ==",
        "seed_node_ids": ["a"],
    }

    evidence = graph_evidence(
        tool="graph_search", query="carry-over", collection_id="g-1", payload=payload, elapsed_ms=5
    )

    assert evidence.kind is EvidenceKind.GRAPH
    assert evidence.graph is not None
    assert [(n.id, n.matched, n.score) for n in evidence.graph.nodes] == [("a", True, 0.0098), ("b", False, None)]
    assert evidence.graph.edges[0].type == "REQUIRES_APPROVAL_FROM"
    assert evidence.model_context == "== Knowledge Graph Context =="


def test_graph_evidence_from_an_entity_list_treats_every_entity_as_matched() -> None:
    payload = [{"id": "a", "name": "Carry-over", "label": "Process"}]

    evidence = graph_evidence(
        tool="graph_entity_search", query="carry", collection_id="g-1", payload=payload, elapsed_ms=None
    )

    assert evidence.graph is not None
    assert [(n.id, n.matched) for n in evidence.graph.nodes] == [("a", True)]


def test_graph_evidence_for_a_neighbourhood_matches_the_centre_entity() -> None:
    payload = {
        "nodes": [{"id": "a", "name": "Carry-over"}, {"id": "b", "name": "HR"}],
        "edges": [{"source": "a", "target": "b", "type": "OWNED_BY"}],
    }

    evidence = graph_evidence(
        tool="graph_neighborhood", query="a", collection_id="g-1", payload=payload, elapsed_ms=None
    )

    assert evidence.graph is not None
    assert [(n.id, n.matched) for n in evidence.graph.nodes] == [("a", True), ("b", False)]


def test_graph_evidence_tolerates_an_unexpected_payload() -> None:
    evidence = graph_evidence(tool="graph_search", query="q", collection_id="g", payload="oops", elapsed_ms=None)

    assert evidence.graph is not None
    assert evidence.graph.nodes == ()


def test_graph_evidence_normalises_edges_from_loose_payloads() -> None:
    payload = {
        "nodes": [{"id": "alice", "name": "Alice"}, {"id": "acme", "name": "Acme"}],
        "edges": [{"source": "alice", "target": "acme"}, {"source": "alice"}],
    }

    evidence = graph_evidence(tool="graph_neighborhood", query="alice", collection_id="g", payload=payload, elapsed_ms=None)

    assert evidence.graph is not None
    assert [(e.source, e.target, e.type) for e in evidence.graph.edges] == [("alice", "acme", "RELATED_TO")]
