from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

import pytest
from error_contract import NotFoundError

from src.retrieval.contract import (
    GraphEdgeView,
    GraphNodeView,
    RetrievalGraph,
    RetrievalHit,
    RetrievalKind,
    RetrievalResult,
)
from src.search import router as search_router
from src.search.models import SearchableCollection, SourceType
from src.search.service import KnowledgeSearchService
from src.server import APP
from src.shared import auth
from tests.unit_tests.fixtures import gateway_headers, get_async_test_client

LEGAL = SearchableCollection(
    identifier="legal",
    name="Legal",
    source_type=SourceType.DOCUMENT,
    connector_type="",
    sync_status="idle",
    has_graph=True,
)
GRAPH = RetrievalGraph(
    nodes=(
        GraphNodeView(
            identifier="p",
            name="Retention policy",
            label="Policy",
            matched=True,
            score=0.03,
            properties={"version": "v3"},
        ),
        GraphNodeView(
            identifier="r",
            name="DPO",
            label="Role",
            matched=False,
            score=None,
            properties={},
        ),
    ),
    edges=(
        GraphEdgeView(
            identifier="pr",
            source="p",
            target="r",
            type="OWNED_BY",
            properties={},
        ),
    ),
)


@dataclass
class StubPorts:
    kinds: list[RetrievalKind] = field(default_factory=list)
    users: list[str] = field(default_factory=list)
    readable: bool = True
    graph_unreachable: bool = False

    async def list_searchable(self, user_id: str) -> tuple[SearchableCollection, ...]:
        """Return one graph-backed collection."""
        self.users.append(user_id)
        if self.graph_unreachable:
            return (replace(LEGAL, has_graph=False, graph_unreachable=True),)
        return (LEGAL,)

    async def retrieve(
        self,
        collection: SearchableCollection,
        *,
        user_id: str,
        query: str,
        kind: RetrievalKind,
        limit: int,
    ) -> RetrievalResult:
        """Answer vector and graph retrieval from fixtures."""
        self.kinds.append(kind)
        hits = (
            ()
            if kind is RetrievalKind.GRAPH
            else (
                RetrievalHit(
                    identifier="c1",
                    content="Keep supplier data for two years.",
                    score=0.42,
                    source="vector",
                    metadata={
                        "source": "Retention.pdf",
                        "page": 3,
                        "section": "4.2",
                        "file_id": "f-1",
                    },
                ),
            )
        )
        return RetrievalResult(
            kind=kind,
            collection_id=collection.identifier,
            hits=hits,
            context="",
            collection_name=collection.name,
            graph=GRAPH if kind is RetrievalKind.GRAPH else None,
        )

    async def ensure_readable(self, user_id: str, collection_id: str) -> None:
        """Deny unreadable collections the way the store adapter does."""
        if not self.readable:
            raise NotFoundError(message="Collection not found")

    async def expand(
        self, collection_id: str, node_id: str, *, depth: int, limit: int
    ) -> RetrievalGraph:
        """Return the fixture graph."""
        return GRAPH


@pytest.fixture
def ports() -> Iterator[StubPorts]:
    stub = StubPorts()
    APP.dependency_overrides[search_router.get_knowledge_search_service] = lambda: (
        KnowledgeSearchService(catalog=stub, retriever=stub, neighborhood=stub)
    )
    yield stub
    APP.dependency_overrides.pop(search_router.get_knowledge_search_service, None)


def _allow_graph(monkeypatch: pytest.MonkeyPatch, *, allowed: bool) -> None:
    async def permission(user_id: str, access_token: str | None) -> bool:
        return allowed

    monkeypatch.setattr(search_router, "has_graph_search_permission", permission)


async def test_search_returns_fused_hits_graph_and_facets(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=True)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "retention", "limit": 10},
            headers=gateway_headers("user-7"),
        )

    assert response.status_code == 200
    body = response.json()
    assert ports.users == ["user-7"]
    assert body["kind"] == "hybrid"
    assert body["graph_available"] is True
    assert body["total"] == 2
    document, entity = body["hits"]
    assert document["kind"] == "document"
    assert document["relevance"] == 1.0
    assert document["document"] == {
        "content": "Keep supplier data for two years.",
        "file_id": "f-1",
        "source": "Retention.pdf",
        "title": None,
        "page": 3,
        "section": "4.2",
        "file_type": "pdf",
        "metadata": {
            "source": "Retention.pdf",
            "page": 3,
            "section": "4.2",
            "file_id": "f-1",
        },
    }
    assert document["entity"] is None
    assert entity["entity"]["relations"] == [
        {
            "type": "OWNED_BY",
            "direction": "out",
            "node_id": "r",
            "node_name": "DPO",
            "node_label": "Role",
        }
    ]
    assert entity["entity"]["neighbor_count"] == 1
    assert body["graph"]["nodes"][0]["collection_id"] == "legal"
    assert body["graph"]["edges"][0]["type"] == "OWNED_BY"
    assert body["collections"] == [
        {
            "id": "legal",
            "name": "Legal",
            "document_hits": 1,
            "entity_hits": 1,
            "status": "ok",
        }
    ]
    assert body["facets"] == {
        "file_types": [{"value": "pdf", "count": 1}],
        "entity_labels": [{"value": "Policy", "count": 1}],
    }
    assert isinstance(body["elapsed_ms"], int)


async def test_search_passes_filters(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=True)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={
                "query": "retention",
                "collection_ids": ["legal"],
                "file_types": ["docx"],
                "entity_labels": ["Role"],
            },
            headers=gateway_headers(),
        )

    assert response.status_code == 200
    assert response.json()["hits"] == []
    assert response.json()["facets"]["file_types"] == [{"value": "pdf", "count": 1}]


async def test_vector_search_skips_graph_permission_check(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    async def fail(user_id: str, access_token: str | None) -> bool:
        raise AssertionError("graph permission must not be checked")

    monkeypatch.setattr(search_router, "has_graph_search_permission", fail)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "retention", "kind": "vector"},
            headers=gateway_headers(),
        )

    assert response.status_code == 200
    assert ports.kinds == [RetrievalKind.VECTOR]


async def test_graph_search_without_permission_is_forbidden(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=False)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "retention", "kind": "graph"},
            headers=gateway_headers(),
        )

    assert response.status_code == 403


async def test_hybrid_without_graph_permission_degrades(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=False)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "retention"},
            headers=gateway_headers(),
        )

    assert response.status_code == 200
    assert response.json()["graph_available"] is False
    assert ports.kinds == [RetrievalKind.VECTOR]


async def test_search_reports_an_unreachable_graph_store(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=True)
    ports.graph_unreachable = True

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search", json={"query": "retention"}, headers=gateway_headers()
        )

    body = response.json()
    assert response.status_code == 200
    assert body["graph_available"] is False
    assert body["graph_unavailable"] is True


async def test_search_graph_store_is_available_by_default(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    _allow_graph(monkeypatch, allowed=True)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search", json={"query": "retention"}, headers=gateway_headers()
        )

    assert response.json()["graph_unavailable"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "q", "limit": 0},
        {"query": "q", "limit": 101},
        {"query": "q", "kind": "web"},
        {"query": "q", "unexpected": True},
        {"query": "q", "collection_ids": [""]},
        {"query": "q", "file_types": ["x"] * 21},
    ],
)
async def test_search_rejects_invalid_payloads(
    ports: StubPorts, payload: dict[str, object]
) -> None:
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search", json=payload, headers=gateway_headers()
        )

    assert response.status_code == 422


async def test_internal_caller_must_delegate_a_user(
    monkeypatch: pytest.MonkeyPatch, ports: StubPorts
) -> None:
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search",
            json={"query": "q", "kind": "vector"},
            headers={"X-Internal-Service-Token": "internal-token"},
        )

    assert response.status_code == 403
    assert ports.users == []


async def test_sources_lists_searchable_collections(ports: StubPorts) -> None:
    async with get_async_test_client() as client:
        response = await client.get(
            "/api/v1/search/sources", headers=gateway_headers("user-3")
        )

    assert response.status_code == 200
    assert response.json() == {
        "sources": [
            {
                "id": "legal",
                "name": "Legal",
                "source_type": "document",
                "connector_type": "",
                "sync_status": "idle",
                "has_graph": True,
            }
        ]
    }
    assert ports.users == ["user-3"]


async def test_neighborhood_returns_unmatched_graph(ports: StubPorts) -> None:
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search/graph/neighborhood",
            json={"collection_id": "legal", "node_ids": ["p"], "depth": 2},
            headers=gateway_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["p", "r"]
    assert not any(node["matched"] for node in body["nodes"])
    assert body["edges"][0]["collection_id"] == "legal"


async def test_neighborhood_of_unreadable_collection_is_not_found(
    ports: StubPorts,
) -> None:
    ports.readable = False

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search/graph/neighborhood",
            json={"collection_id": "secret", "node_ids": ["p"]},
            headers=gateway_headers(),
        )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"collection_id": "legal", "node_ids": []},
        {"collection_id": "legal", "node_ids": ["n"] * 21},
        {"collection_id": "legal", "node_ids": ["n"], "depth": 4},
        {"collection_id": "legal", "node_ids": ["n"], "limit": 301},
    ],
)
async def test_neighborhood_rejects_invalid_payloads(
    ports: StubPorts, payload: dict[str, object]
) -> None:
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/search/graph/neighborhood",
            json=payload,
            headers=gateway_headers(),
        )

    assert response.status_code == 422


def test_default_service_factory_wires_store_adapters() -> None:
    service = search_router.get_knowledge_search_service()

    assert isinstance(service, KnowledgeSearchService)
