from __future__ import annotations

import logging
from typing import ClassVar
from unittest.mock import AsyncMock

import httpx
import pytest
from error_contract import ForbiddenError, NotFoundError, ValidationFailedError
from neo4j.exceptions import ServiceUnavailable
from pymilvus import MilvusException

from src.graph.schemas import GraphData, GraphEdge, GraphNode
from src.retrieval import adapters as retrieval_adapters
from src.retrieval.contract import (
    GraphRetrieval,
    RetrievalKind,
    VectorDocument,
)
from src.search import adapters
from src.search.models import SearchableCollection, SourceType
from src.search.ports import CollectionSearchError


def _collection(uuid: str, name: str, **metadata: object) -> dict[str, object]:
    return {"uuid": uuid, "name": name, "metadata": dict(metadata)}


class _Manager:
    rows: ClassVar[list[dict[str, object]]] = []

    def __init__(self, user_id: str) -> None:
        """Remember the caller."""
        self.user_id = user_id

    async def list(self) -> list[dict[str, object]]:
        """Return the configured rows."""
        return self.rows


async def test_catalog_describes_readable_collections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Manager.rows = [
        _collection("b", "Policies"),
        _collection("a", "raw", friendly_name="Drive", connector_type="gdrive"),
    ]
    monkeypatch.setattr(adapters, "CollectionsManager", _Manager)
    monkeypatch.setattr(
        adapters.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(return_value=["b", "foreign"]),
    )

    sources = await adapters.CollectionsSearchCatalog().list_searchable("user")

    assert sources == (
        SearchableCollection(
            identifier="a",
            name="Drive",
            source_type=SourceType.CONNECTOR,
            connector_type="gdrive",
            sync_status="idle",
            has_graph=False,
        ),
        SearchableCollection(
            identifier="b",
            name="Policies",
            source_type=SourceType.DOCUMENT,
            connector_type="",
            sync_status="idle",
            has_graph=True,
        ),
    )


async def test_catalog_survives_graph_store_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Manager.rows = [_collection("b", "Policies")]
    monkeypatch.setattr(adapters, "CollectionsManager", _Manager)
    monkeypatch.setattr(
        adapters.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(side_effect=ConnectionError("neo4j down")),
    )

    (source,) = await adapters.CollectionsSearchCatalog().list_searchable("user")

    assert source.has_graph is False
    assert source.graph_unreachable is True


async def test_catalog_logs_the_graph_store_outage_with_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _Manager.rows = [_collection("b", "Policies")]
    monkeypatch.setattr(adapters, "CollectionsManager", _Manager)
    monkeypatch.setattr(
        adapters.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(side_effect=ServiceUnavailable("neo4j down")),
    )

    with caplog.at_level(logging.WARNING):
        await adapters.CollectionsSearchCatalog().list_searchable("user")

    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record.exc_info is not None


async def test_catalog_does_not_hide_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Manager.rows = [_collection("b", "Policies")]
    monkeypatch.setattr(adapters, "CollectionsManager", _Manager)
    monkeypatch.setattr(
        adapters.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(side_effect=TypeError("bug")),
    )

    with pytest.raises(TypeError):
        await adapters.CollectionsSearchCatalog().list_searchable("user")


async def test_catalog_flags_reachable_graph_store_as_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Manager.rows = [_collection("b", "Policies")]
    monkeypatch.setattr(adapters, "CollectionsManager", _Manager)
    monkeypatch.setattr(
        adapters.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(return_value=[]),
    )

    (source,) = await adapters.CollectionsSearchCatalog().list_searchable("user")

    assert source.graph_unreachable is False


class _Unreachable:
    def __init__(self, user_id: str) -> None:
        """Fail loudly: the catalog already vetted the collection."""
        raise AssertionError("collection access was checked again")


COLLECTION = SearchableCollection(
    identifier="col",
    name="Legal",
    source_type=SourceType.DOCUMENT,
    connector_type="",
    sync_status="idle",
    has_graph=True,
)


async def test_retriever_runs_vector_contract_without_reauthorizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vectors = AsyncMock(
        return_value=(
            VectorDocument(
                identifier="c1",
                content="text",
                score=0.1,
                metadata={"source": "a.pdf", "api_key": "secret"},
            ),
        )
    )
    monkeypatch.setattr(adapters, "search_collection_vectors", vectors)
    monkeypatch.setattr(
        retrieval_adapters,
        "CollectionsManager",
        _Unreachable,
    )

    result = await adapters.RetrievalContractRetriever().retrieve(
        COLLECTION,
        user_id="user",
        query="q",
        kind=RetrievalKind.VECTOR,
        limit=5,
    )

    vectors.assert_awaited_once_with("col", "user", "q", limit=5)
    assert result.collection_name == "Legal"
    assert result.hits[0].metadata["api_key"] == "***REDACTED***"


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("down"),
        TimeoutError("slow"),
        MilvusException(message="milvus down"),
        ServiceUnavailable("neo4j down"),
        httpx.ConnectError("embedder down"),
        NotFoundError(message="gone"),
    ],
)
async def test_retriever_translates_store_failures(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setattr(
        adapters, "search_collection_vectors", AsyncMock(side_effect=failure)
    )

    with pytest.raises(CollectionSearchError):
        await adapters.RetrievalContractRetriever().retrieve(
            COLLECTION, user_id="user", query="q", kind=RetrievalKind.VECTOR, limit=5
        )


@pytest.mark.parametrize(
    "failure",
    [ForbiddenError(message="mismatch"), ValidationFailedError(message="bad request")],
)
async def test_retriever_does_not_hide_contract_violations(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """A forbidden or invalid retrieval is a caller bug, not a store outage."""
    monkeypatch.setattr(
        adapters, "search_collection_vectors", AsyncMock(side_effect=failure)
    )

    with pytest.raises(type(failure)):
        await adapters.RetrievalContractRetriever().retrieve(
            COLLECTION, user_id="user", query="q", kind=RetrievalKind.VECTOR, limit=5
        )


async def test_retriever_does_not_hide_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapters, "search_collection_vectors", AsyncMock(side_effect=TypeError("bug"))
    )

    with pytest.raises(TypeError):
        await adapters.RetrievalContractRetriever().retrieve(
            COLLECTION, user_id="user", query="q", kind=RetrievalKind.VECTOR, limit=5
        )


async def test_retriever_runs_graph_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = AsyncMock(
        return_value=GraphRetrieval(nodes=(), edges=(), context="", score=0.0)
    )
    monkeypatch.setattr(adapters, "search_collection_graph", graph)

    result = await adapters.RetrievalContractRetriever().retrieve(
        COLLECTION,
        user_id="user",
        query="q",
        kind=RetrievalKind.GRAPH,
        limit=7,
    )

    graph.assert_awaited_once_with("col", "user", "q", limit=7)
    assert result.graph is not None


async def test_neighborhood_checks_read_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure = AsyncMock()
    created: list[tuple[str, str]] = []

    class FakeCollection:
        def __init__(self, collection_id: str, user_id: str) -> None:
            created.append((collection_id, user_id))
            self.ensure_exists = ensure

    monkeypatch.setattr(adapters, "Collection", FakeCollection)

    await adapters.GraphStoreNeighborhood().ensure_readable("user", "col")

    assert created == [("col", "user")]
    ensure.assert_awaited_once_with("read")


async def test_neighborhood_maps_graph_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = GraphData(
        nodes=[
            GraphNode(id="a", label="Role", name="A", properties={"password": "x"}),
            GraphNode(id="b", label="Role", name="B", properties={}),
        ],
        edges=[GraphEdge(id="ab", source="a", target="b", type="R", properties={})],
    )
    neighborhood = AsyncMock(return_value=data)

    class FakeStore:
        def __init__(self, collection_id: str) -> None:
            self.collection_id = collection_id
            self.get_neighborhood = neighborhood

    monkeypatch.setattr(adapters, "GraphStore", FakeStore)

    graph = await adapters.GraphStoreNeighborhood().expand(
        "col", "a", depth=2, limit=40
    )

    neighborhood.assert_awaited_once_with(node_id="a", depth=2, limit=40)
    assert [(node.identifier, node.matched) for node in graph.nodes] == [
        ("a", False),
        ("b", False),
    ]
    assert graph.nodes[0].properties["password"] == "***REDACTED***"
    assert graph.edges[0].identifier == "ab"
