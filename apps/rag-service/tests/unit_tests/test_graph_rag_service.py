from __future__ import annotations

import pytest

from src.graph.repositories.search_repository import (
    relationship_type_candidates,
)
from src.graph.schemas import GraphData, GraphEdge, GraphNode
from src.graph.service import GraphRAGService
from src.graph.service import GraphRAGService, _missing_endpoints


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

    async def fake_fetch_subgraph_for_names(node_names: list[str], *, limit: int):
        return GraphData(nodes=[], edges=[])

    async def fake_entity_context(entity_names: list[str]):
        return "Knowledge Graph Context:\nTelekomünikasyon --[HAS]--> Türksat"

    monkeypatch.setattr(service, "_vector_search", fake_vector_search)
    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)
    monkeypatch.setattr(
        service.graph_store,
        "fetch_subgraph_for_names",
        fake_fetch_subgraph_for_names,
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

    async def fake_fetch_subgraph_for_names(node_names: list[str], *, limit: int):
        return GraphData(nodes=[], edges=[])

    async def fake_entity_context(entity_names: list[str]):
        return ""

    monkeypatch.setattr(service, "_vector_search", fake_vector_search)
    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)
    monkeypatch.setattr(
        service.graph_store,
        "search_relationships_by_type",
        fake_relationship_search,
        raising=False,
    )
    monkeypatch.setattr(
        service.graph_store, "fetch_subgraph_for_names", fake_fetch_subgraph_for_names
    )
    monkeypatch.setattr(
        service.graph_store, "get_entity_context_focused", fake_entity_context
    )

    async def no_extra_subgraph(*args: object, **kwargs: object):
        return GraphData(nodes=[], edges=[])

    async def no_extra_context(*args: object, **kwargs: object):
        return ""

    monkeypatch.setattr(service.graph_store, "fetch_subgraph_for_names", no_extra_subgraph)
    monkeypatch.setattr(
        service.graph_store, "get_entity_context_focused", no_extra_context
    )

    result = await service.hybrid_search("genel müdürleri kimdir")

    assert [edge.type for edge in result.edges] == [
        "GENERAL_MANAGER",
        "GENERAL_MANAGER",
    ]
    assert "Türksat --[GENERAL_MANAGER]--> Ahmet Hamdi Atalay" in result.context
    assert "Türksat --[GENERAL_MANAGER]--> Hasan Hüseyin Ertok" in result.context
    assert result.score > 0


def _bm25_hit(node_id: str, name: str, score: float = 3.0) -> dict:
    return {
        "node": GraphNode(id=node_id, label="Process", name=name, properties={}),
        "bm25_score": score,
    }


def _patch_graph_store(
    monkeypatch: pytest.MonkeyPatch,
    service: GraphRAGService,
    *,
    bm25: list[dict],
    subgraph: GraphData,
    relationships: GraphData | None = None,
) -> None:
    async def fake_bm25_search(query: str, *, limit: int):
        return bm25

    async def fake_subgraph(node_names: list[str], *, limit: int):
        return subgraph

    async def fake_relationship_search(query: str, *, limit: int):
        return relationships or GraphData(nodes=[], edges=[])

    async def fake_entity_context(entity_names: list[str]):
        return ""

    monkeypatch.setattr(service, "_graph_bm25_search", fake_bm25_search)
    monkeypatch.setattr(service.graph_store, "fetch_subgraph_for_names", fake_subgraph)
    monkeypatch.setattr(
        service.graph_store,
        "search_relationships_by_type",
        fake_relationship_search,
        raising=False,
    )
    monkeypatch.setattr(
        service.graph_store, "get_entity_context_focused", fake_entity_context
    )


async def test_hybrid_search_includes_every_edge_endpoint_as_a_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphRAGService("collection-id")
    manager = GraphNode(id="b", label="Role", name="Line Manager", properties={})
    _patch_graph_store(
        monkeypatch,
        service,
        bm25=[_bm25_hit("a", "Annual Leave Carry-over")],
        subgraph=GraphData(
            nodes=[
                GraphNode(
                    id="a",
                    label="Process",
                    name="Annual Leave Carry-over",
                    properties={},
                ),
                manager,
            ],
            edges=[
                GraphEdge(
                    id="e1",
                    source="a",
                    target="b",
                    type="REQUIRES_APPROVAL_FROM",
                    properties={},
                )
            ],
        ),
    )

    result = await service.hybrid_search("annual leave carry-over approval")

    node_ids = {node.id for node in result.nodes}
    assert node_ids == {"a", "b"}
    assert all(
        edge.source in node_ids and edge.target in node_ids for edge in result.edges
    )


async def test_hybrid_search_reports_query_matched_nodes_as_seeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GraphRAGService("collection-id")
    _patch_graph_store(
        monkeypatch,
        service,
        bm25=[_bm25_hit("a", "Annual Leave Carry-over")],
        subgraph=GraphData(
            nodes=[
                GraphNode(
                    id="a",
                    label="Process",
                    name="Annual Leave Carry-over",
                    properties={},
                ),
                GraphNode(id="b", label="Role", name="Line Manager", properties={}),
            ],
            edges=[GraphEdge(id="e1", source="a", target="b", type="R", properties={})],
        ),
        relationships=GraphData(
            nodes=[
                GraphNode(id="c", label="Organization", name="Acme", properties={}),
                GraphNode(id="d", label="Person", name="Jane", properties={}),
            ],
            edges=[
                GraphEdge(
                    id="e2",
                    source="c",
                    target="d",
                    type="GENERAL_MANAGER",
                    properties={},
                )
            ],
        ),
    )

    result = await service.hybrid_search("annual leave")

    assert result.seed_node_ids == ["a", "c", "d"]
    assert "b" not in result.seed_node_ids


async def test_hybrid_search_lists_query_matches_before_expanded_neighbours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Consumers that keep the first N nodes (retrieval hits, evidence caps)
    must still get the query's own matches when neighbours are appended.
    """
    service = GraphRAGService("collection-id")
    neighbours = [
        GraphNode(id=f"n{i}", label="Role", name=f"Neighbour {i}", properties={})
        for i in range(5)
    ]
    _patch_graph_store(
        monkeypatch,
        service,
        bm25=[
            _bm25_hit("a", "Annual Leave Carry-over"),
            _bm25_hit("b", "Carry-over Limit"),
        ],
        subgraph=GraphData(
            nodes=neighbours,
            edges=[
                GraphEdge(
                    id=f"e{i}", source="a", target=f"n{i}", type="R", properties={}
                )
                for i in range(5)
            ],
        ),
    )

    result = await service.hybrid_search("carry-over", limit=2)

    assert [node.id for node in result.nodes[:2]] == result.seed_node_ids == ["a", "b"]
    assert {node.id for node in result.nodes[2:]} == {f"n{i}" for i in range(5)}


def test_missing_endpoints_returns_each_unknown_node_once_without_mutating_known():
    pool = [
        GraphNode(id="a", label="L", name="A", properties={}),
        GraphNode(id="b", label="L", name="B", properties={}),
        GraphNode(id="b", label="L", name="B", properties={}),
        GraphNode(id="c", label="L", name="C", properties={}),
    ]
    edges = [GraphEdge(id="e", source="a", target="b", type="R", properties={})]
    known = {"a"}

    missing = _missing_endpoints(edges, known=known, pool=pool)

    assert [node.id for node in missing] == ["b"]
    assert known == {"a"}
