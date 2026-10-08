from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from error_contract import ForbiddenError

from src.graph.schemas import (
    GraphData,
    GraphEdge,
    GraphNode,
    GraphSearchResult,
)
from src.retrieval import adapters
from src.retrieval.contract import AuthorizedCollection
from src.shared.auth import AuthenticatedUser


def _request(headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(headers=headers)


def test_graph_retrieval_from_search_result_marks_seed_nodes() -> None:
    search_result = GraphSearchResult(
        nodes=[
            GraphNode(
                id="a",
                label="Process",
                name="Carry-over",
                properties={"rrf_score": 0.0098},
            ),
            GraphNode(id="b", label="Role", name="Line Manager", properties={}),
        ],
        edges=[
            GraphEdge(id="e1", source="a", target="b", type="R", properties={}),
        ],
        context="ctx",
        score=0.6,
        seed_node_ids=["a"],
    )

    graph = adapters.graph_retrieval_from_search_result(search_result)

    assert [(node.identifier, node.matched) for node in graph.nodes] == [
        ("a", True),
        ("b", False),
    ]
    assert graph.nodes[0].score == 0.0098
    assert graph.nodes[1].score is None
    assert graph.edges[0].source == "a"
    assert graph.context == "ctx"


async def test_search_collection_vectors_maps_store_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = AsyncMock(
        return_value=[
            {"id": 7, "page_content": "text", "metadata": {"a": 1}, "score": 0.4},
            {"id": None, "page_content": None, "metadata": None, "score": None},
        ]
    )
    created: list[tuple[str, str]] = []

    class FakeCollection:
        def __init__(self, *, collection_id: str, user_id: str) -> None:
            created.append((collection_id, user_id))
            self.search = search

    monkeypatch.setattr(adapters, "Collection", FakeCollection)

    documents = await adapters.search_collection_vectors(
        "col-1", "user-1", "query", limit=3
    )

    assert created == [("col-1", "user-1")]
    search.assert_awaited_once_with("query", limit=3)
    assert documents[0].identifier == "7"
    assert documents[0].metadata == {"a": 1}
    assert (documents[1].identifier, documents[1].content) == (None, "")
    assert (documents[1].score, documents[1].metadata) == (0.0, {})


async def test_search_collection_vectors_identifies_hits_by_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two chunks of one file must stay two hits, not share the file id."""
    rows = [
        {"id": "file-1", "chunk_id": "11", "page_content": "a", "metadata": {}},
        {"id": "file-1", "chunk_id": "12", "page_content": "b", "metadata": {}},
    ]

    class FakeCollection:
        def __init__(self, *, collection_id: str, user_id: str) -> None:
            self.search = AsyncMock(return_value=rows)

    monkeypatch.setattr(adapters, "Collection", FakeCollection)

    documents = await adapters.search_collection_vectors(
        "col-1", "user-1", "query", limit=3
    )

    assert [document.identifier for document in documents] == ["11", "12"]


async def test_search_collection_graph_runs_hybrid_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = GraphSearchResult(
        nodes=[GraphNode(id="n", label="L", name="N", properties={})],
        edges=[],
        context="c",
        score=0.2,
        seed_node_ids=["n"],
    )
    hybrid = AsyncMock(return_value=result)

    class FakeGraphService:
        def __init__(self, *, collection_id: str, user_id: str) -> None:
            self.hybrid_search = hybrid

    monkeypatch.setattr(adapters, "GraphRAGService", FakeGraphService)

    graph = await adapters.search_collection_graph("col", "user", "q", limit=4)

    hybrid.assert_awaited_once_with("q", limit=4)
    assert graph.nodes[0].matched is True


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        (None, None),
        ({"name": "Legal"}, AuthorizedCollection("col", "Legal")),
    ],
)
async def test_authorize_collection_read(
    monkeypatch: pytest.MonkeyPatch,
    details: dict[str, str] | None,
    expected: AuthorizedCollection | None,
) -> None:
    class FakeManager:
        def __init__(self, user_id: str) -> None:
            self.get = AsyncMock(return_value=details)

    monkeypatch.setattr(adapters, "CollectionsManager", FakeManager)

    assert await adapters.authorize_collection_read("user", "col") == expected


def test_trusted_context_uses_public_identity() -> None:
    user = AuthenticatedUser("user-1", "User One")

    context = adapters.trusted_context_from_request(_request({}), user)

    assert context.user_id == "user-1"


def test_trusted_context_requires_delegation_for_internal_caller() -> None:
    user = AuthenticatedUser("internal-service", "Internal")

    with pytest.raises(ForbiddenError):
        adapters.trusted_context_from_request(_request({}), user)

    context = adapters.trusted_context_from_request(
        _request({"x-user-id": " delegated ", "x-tenant-id": "t"}), user
    )
    assert (context.user_id, context.tenant_id) == ("delegated", "t")


async def test_internal_service_always_has_graph_search_permission() -> None:
    assert await adapters.has_graph_search_permission("internal-service", None)


async def test_graph_search_permission_asks_authorization_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(has_permission=AsyncMock(return_value=False))
    monkeypatch.setattr(adapters, "get_authorization_client", lambda: client)

    assert not await adapters.has_graph_search_permission("user", "token")
    client.has_permission.assert_awaited_once_with("user", "graph:search", "token")


def test_graph_view_from_graph_data_defaults_to_unmatched_nodes() -> None:
    data = GraphData(
        nodes=[GraphNode(id="a", label="Role", name="A", properties={"k": 1})],
        edges=[GraphEdge(id="e", source="a", target="a", type="R", properties={})],
    )

    graph = adapters.graph_view_from_graph_data(data)

    assert [(n.identifier, n.matched, n.score) for n in graph.nodes] == [
        ("a", False, None)
    ]
    assert dict(graph.nodes[0].properties) == {"k": 1}
    assert [(e.identifier, e.source, e.target, e.type) for e in graph.edges] == [
        ("e", "a", "a", "R")
    ]


def test_graph_view_from_graph_data_marks_seeds_and_reads_rrf_score() -> None:
    data = GraphData(
        nodes=[
            GraphNode(id="a", label="L", name="A", properties={"rrf_score": 0.25}),
            GraphNode(id="b", label="L", name="B", properties={}),
        ],
        edges=[],
    )

    graph = adapters.graph_view_from_graph_data(data, seed_ids=["a"])

    assert [(n.identifier, n.matched, n.score) for n in graph.nodes] == [
        ("a", True, 0.25),
        ("b", False, None),
    ]
