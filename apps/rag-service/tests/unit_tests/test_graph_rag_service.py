from __future__ import annotations

import pytest

from langconnect.database.neo4j.repositories.search_repository import (
    relationship_type_candidates,
)
from langconnect.models.graph import GraphData, GraphEdge, GraphNode
from langconnect.services.graph_rag_service import GraphRAGService


@pytest.mark.asyncio
async def test_hybrid_search_does_not_return_vector_only_context_for_graph_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphRAGService("collection-id")

    async def fake_vector_search(query: str, *, limit: int):
        raise AssertionError("Graph-only search must not call vector search")

    async def fake_bm25_search(query: str, *, limit: int):
        return []

    monkeypatch.setattr(service, "_vector_search", fake_vector_search)
    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)

    result = await service.hybrid_search("unmatched natural language query")

    assert result.nodes == []
    assert result.edges == []
    assert result.score == 0
    assert result.context == ""


@pytest.mark.asyncio
async def test_hybrid_search_prioritizes_graph_context_before_vector_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphRAGService("collection-id")

    async def fake_vector_search(query: str, *, limit: int):
        return [
            {
                "id": "chunk-1",
                "content": "Vector supporting content.",
                "score": 0.9,
            },
        ]

    async def fake_bm25_search(query: str, *, limit: int):
        return [
            {
                "node": GraphNode(
                    id="node-1",
                    label="Concept",
                    name="Telekomünikasyon",
                    properties={},
                ),
                "bm25_score": 3.0,
            },
        ]

    async def fake_fetch_edges_for_nodes(node_names: list[str], *, limit: int):
        return []

    async def fake_entity_context(entity_names: list[str]):
        return "Knowledge Graph Context:\nTelekomünikasyon --[HAS]--> Türksat"

    monkeypatch.setattr(service, "_vector_search", fake_vector_search)
    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)
    monkeypatch.setattr(
        service.graph_store,
        "fetch_edges_for_nodes",
        fake_fetch_edges_for_nodes,
    )
    monkeypatch.setattr(
        service.graph_store,
        "get_entity_context_focused",
        fake_entity_context,
    )

    result = await service.hybrid_search(
        "Telekomünikasyon", include_vector_context=True
    )

    assert result.context.startswith("== RRF-Ranked Entities ==")
    assert result.context.index("== Knowledge Graph Context ==") < result.context.index(
        "== Vector Search Results =="
    )


def test_relationship_type_candidates_maps_turkish_general_manager_query() -> None:
    assert relationship_type_candidates("genel müdürleri kimdir") == ["GENERAL_MANAGER"]


@pytest.mark.asyncio
async def test_hybrid_search_returns_relationship_type_matches_without_node_bm25(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphRAGService("collection-id")

    async def fake_vector_search(query: str, *, limit: int):
        return []

    async def fake_bm25_search(query: str, *, limit: int):
        return []

    async def fake_relationship_search(query: str, *, limit: int):
        return GraphData(
            nodes=[
                GraphNode(
                    id="company",
                    label="Organization",
                    name="Türksat",
                    properties={},
                ),
                GraphNode(
                    id="person-1",
                    label="Person",
                    name="Ahmet Hamdi Atalay",
                    properties={},
                ),
                GraphNode(
                    id="person-2",
                    label="Person",
                    name="Hasan Hüseyin Ertok",
                    properties={},
                ),
            ],
            edges=[
                GraphEdge(
                    id="edge-1",
                    source="company",
                    target="person-1",
                    type="GENERAL_MANAGER",
                    properties={},
                ),
                GraphEdge(
                    id="edge-2",
                    source="company",
                    target="person-2",
                    type="GENERAL_MANAGER",
                    properties={},
                ),
            ],
        )

    monkeypatch.setattr(service, "_vector_search", fake_vector_search)
    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)
    monkeypatch.setattr(
        service.graph_store,
        "search_relationships_by_type",
        fake_relationship_search,
        raising=False,
    )

    result = await service.hybrid_search("genel müdürleri kimdir")

    assert [edge.type for edge in result.edges] == [
        "GENERAL_MANAGER",
        "GENERAL_MANAGER",
    ]
    assert "Türksat --[GENERAL_MANAGER]--> Ahmet Hamdi Atalay" in result.context
    assert "Türksat --[GENERAL_MANAGER]--> Hasan Hüseyin Ertok" in result.context
    assert result.score > 0
