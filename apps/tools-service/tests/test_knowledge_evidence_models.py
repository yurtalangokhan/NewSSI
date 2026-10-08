"""Contract tests for the KnowledgeEvidence v1 payload."""

from __future__ import annotations

import math

from pydantic import ValidationError
import pytest

from src.knowledge.evidence import (
    MAX_CHUNK_CHARS,
    MAX_CHUNKS,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_MODEL_CONTEXT_CHARS,
    MAX_PROPERTIES,
    MAX_PROPERTY_VALUE_CHARS,
    EvidenceChunk,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceKind,
    EvidenceSource,
    KnowledgeEvidence,
)

_CHUNK_TEXT = "Kullanılmayan yıllık izin günleri devredilebilir."


def _chunk(ref: int = 1, content: str = _CHUNK_TEXT) -> dict:
    return {
        "ref": ref,
        "id": f"chk_{ref}",
        "score": 0.89,
        "content": content,
        "source": {"document": "İzin Yönetmeliği 2026.pdf", "page": 7},
    }


def _node(node_id: str, *, matched: bool = False) -> dict:
    return {"id": node_id, "name": f"Entity {node_id}", "label": "Process", "matched": matched}


def test_document_evidence_round_trips_through_json() -> None:
    evidence = KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool="database_search",
        query="yıllık izin devri",
        collections=[{"id": "col-1", "name": "İK Politikaları"}],
        chunks=[_chunk()],
        model_context="[1] (İzin Yönetmeliği 2026.pdf)\nKullanılmayan yıllık izin...",
        elapsed_ms=420,
    )

    restored = KnowledgeEvidence.model_validate(evidence.model_dump(mode="json"))

    assert restored == evidence
    assert restored.schema_version == 1
    assert restored.chunks[0].source.document == "İzin Yönetmeliği 2026.pdf"


def test_chunk_content_over_limit_is_truncated_and_flagged() -> None:
    chunk = EvidenceChunk.model_validate(_chunk(content="x" * (MAX_CHUNK_CHARS + 50)))

    assert len(chunk.content) == MAX_CHUNK_CHARS
    assert chunk.truncated is True


def test_chunk_content_within_limit_is_not_flagged() -> None:
    chunk = EvidenceChunk.model_validate(_chunk(content="short"))

    assert chunk.truncated is False


def test_chunk_list_is_capped() -> None:
    evidence = KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool="database_search",
        query="q",
        chunks=[_chunk(ref=i + 1) for i in range(MAX_CHUNKS + 5)],
    )

    assert len(evidence.chunks) == MAX_CHUNKS


def test_model_context_over_limit_is_truncated_and_flagged() -> None:
    evidence = KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool="database_search",
        query="q",
        model_context="y" * (MAX_MODEL_CONTEXT_CHARS + 1),
    )

    assert len(evidence.model_context) == MAX_MODEL_CONTEXT_CHARS
    assert evidence.model_context_truncated is True


def test_source_keeps_only_whitelisted_fields() -> None:
    chunk = EvidenceChunk.model_validate(
        {
            **_chunk(),
            "source": {
                "document": "a.pdf",
                "access_token": "secret",
                "internal_path": "/srv/uploads/a.pdf",
            },
        }
    )

    dumped = chunk.source.model_dump()
    assert dumped["document"] == "a.pdf"
    assert "access_token" not in dumped
    assert "internal_path" not in dumped


def test_non_finite_score_becomes_none() -> None:
    chunk = EvidenceChunk.model_validate({**_chunk(), "score": math.nan})

    assert chunk.score is None


def test_graph_drops_edges_whose_endpoints_are_not_nodes() -> None:
    graph = EvidenceGraph(
        nodes=[_node("n1", matched=True), _node("n2")],
        edges=[
            {"source": "n1", "target": "n2", "type": "REQUIRES_APPROVAL_FROM"},
            {"source": "n1", "target": "ghost", "type": "OWNED_BY"},
        ],
    )

    assert [edge.type for edge in graph.edges] == ["REQUIRES_APPROVAL_FROM"]


def test_graph_nodes_and_edges_are_capped() -> None:
    nodes = [_node(f"n{i}") for i in range(MAX_GRAPH_NODES + 10)]
    edges = [
        {"source": "n0", "target": f"n{i % MAX_GRAPH_NODES}", "type": "RELATES_TO"}
        for i in range(MAX_GRAPH_EDGES + 10)
    ]

    graph = EvidenceGraph(nodes=nodes, edges=edges)

    assert len(graph.nodes) == MAX_GRAPH_NODES
    assert len(graph.edges) == MAX_GRAPH_EDGES


def test_graph_node_properties_are_sanitized() -> None:
    node = EvidenceGraphNode.model_validate(
        {
            **_node("n1"),
            "properties": {
                "description": "d" * (MAX_PROPERTY_VALUE_CHARS + 10),
                "password": "hunter2",
                "api_key": "k",
                "_internal": 1,
                "aliases": ["A", "B"],
                "weight": 3,
                **{f"extra_{i}": i for i in range(MAX_PROPERTIES + 5)},
            },
        }
    )

    properties = node.properties
    assert "password" not in properties
    assert "api_key" not in properties
    assert "_internal" not in properties
    assert len(properties["description"]) == MAX_PROPERTY_VALUE_CHARS
    assert properties["aliases"] == '["A", "B"]'
    assert properties["weight"] == 3
    assert len(properties) <= MAX_PROPERTIES


def test_edge_properties_are_sanitized() -> None:
    edge = EvidenceGraphEdge.model_validate(
        {"source": "a", "target": "b", "type": "T", "properties": {"secret": "s", "since": 2024}}
    )

    assert edge.properties == {"since": 2024}


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        KnowledgeEvidence.model_validate(
            {"schema_version": 2, "kind": "document", "tool": "database_search", "query": "q"}
        )


def test_unknown_top_level_fields_are_ignored_for_forward_compatibility() -> None:
    evidence = KnowledgeEvidence.model_validate(
        {"kind": "graph", "tool": "graph_search", "query": "q", "future_field": {"a": 1}}
    )

    assert evidence.kind is EvidenceKind.GRAPH


def test_evidence_is_immutable() -> None:
    evidence = KnowledgeEvidence(kind=EvidenceKind.DOCUMENT, tool="database_search", query="q")

    with pytest.raises(ValidationError):
        evidence.query = "changed"  # type: ignore[misc]


def test_source_from_vector_store_metadata() -> None:
    source = EvidenceSource.from_metadata(
        {
            "source": "İzin Yönetmeliği 2026.pdf",
            "title": "İzin Yönetmeliği",
            "page": "7",
            "file_id": "file-1",
            "token_count": 212,
        }
    )

    assert source == EvidenceSource(
        document="İzin Yönetmeliği 2026.pdf",
        title="İzin Yönetmeliği",
        page=7,
        file_id="file-1",
    )


def test_source_from_metadata_accepts_page_number_and_ignores_junk() -> None:
    assert EvidenceSource.from_metadata({"page_number": 3, "title": ""}).page == 3
    assert EvidenceSource.from_metadata({"page": True}).page is None
    assert EvidenceSource.from_metadata({"page": "iv"}).page is None
    assert EvidenceSource.from_metadata(None) == EvidenceSource()


def test_chunk_from_hit_maps_source_metadata_and_collection() -> None:
    chunk = EvidenceChunk.from_hit(
        ref=2,
        collection_id="col-1",
        content="body",
        hit_id="chunk-9",
        score=0.42,
        metadata={"source": "policy.pdf", "page": "7", "token_count": 212},
    )

    assert chunk == EvidenceChunk(
        ref=2,
        id="chunk-9",
        score=0.42,
        content="body",
        collection_id="col-1",
        source=EvidenceSource(document="policy.pdf", page=7),
    )


def test_chunk_from_hit_defaults_to_an_empty_source() -> None:
    chunk = EvidenceChunk.from_hit(ref=1, collection_id="col-1", content="body")

    assert chunk.id is None
    assert chunk.score is None
    assert chunk.source == EvidenceSource()


def test_golden_v1_payload_round_trips_unchanged():
    import json
    from pathlib import Path

    from src.knowledge.evidence import KnowledgeEvidence

    golden = json.loads(
        (Path(__file__).resolve().parents[3] / "docs/contracts/knowledge-evidence.v1.json").read_text()
    )
    assert KnowledgeEvidence.model_validate(golden).model_dump(mode="json") == golden
