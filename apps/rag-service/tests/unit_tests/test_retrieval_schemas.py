from __future__ import annotations

from src.retrieval.contract import (
    GraphEdgeView,
    GraphNodeView,
    RetrievalGraph,
    RetrievalHit,
    RetrievalKind,
    RetrievalResult,
)
from src.retrieval.schemas import (
    RetrievalGraphBody,
    RetrievalGraphEdgeBody,
    RetrievalGraphNodeBody,
    RetrievalResponseBody,
)
from src.search.schemas import SearchGraphEdgeBody, SearchGraphNodeBody

GRAPH = RetrievalGraph(
    nodes=(GraphNodeView("a", "A", "Role", True, 0.5, {"k": 1}),),
    edges=(GraphEdgeView("e", "a", "a", "SELF", {"w": 2}),),
)


def test_graph_body_maps_nodes_and_edges() -> None:
    body = RetrievalGraphBody.from_graph(GRAPH)

    assert body.nodes[0].model_dump() == {
        "id": "a",
        "name": "A",
        "label": "Role",
        "matched": True,
        "score": 0.5,
        "properties": {"k": 1},
    }
    assert body.edges[0].model_dump() == {
        "id": "e",
        "source": "a",
        "target": "a",
        "type": "SELF",
        "properties": {"w": 2},
    }


def test_response_body_maps_result_with_and_without_graph() -> None:
    hit = RetrievalHit("h", "text", 0.1, "vector", {"source": "a.pdf"})
    result = RetrievalResult(
        kind=RetrievalKind.HYBRID,
        collection_id="col",
        hits=(hit,),
        context="ctx",
        collection_name="Legal",
        graph=GRAPH,
    )

    body = RetrievalResponseBody.from_result(result)

    assert (body.kind, body.collection_id, body.collection_name) == (
        "hybrid",
        "col",
        "Legal",
    )
    assert body.hits[0].metadata == {"source": "a.pdf"}
    assert body.graph is not None
    assert (
        RetrievalResponseBody.from_result(
            RetrievalResult(RetrievalKind.VECTOR, "col", (), "")
        ).graph
        is None
    )


def test_search_graph_bodies_extend_the_retrieval_bodies_with_the_collection() -> None:
    node = SearchGraphNodeBody(
        id="a",
        name="A",
        label="Role",
        matched=True,
        score=None,
        collection_id="col",
        properties={},
    )
    edge = SearchGraphEdgeBody(
        id=None,
        source="a",
        target="b",
        type="R",
        collection_id="col",
        properties={},
    )

    assert node.model_dump()["collection_id"] == "col"
    assert edge.model_dump()["collection_id"] == "col"
    assert isinstance(node, RetrievalGraphNodeBody)
    assert isinstance(edge, RetrievalGraphEdgeBody)
