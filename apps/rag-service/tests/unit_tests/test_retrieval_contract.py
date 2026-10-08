from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from error_contract import ForbiddenError, ValidationFailedError

from src.retrieval import service as retrieval
from src.retrieval.contract import (
    MAX_LIMIT,
    AuthorizedCollection,
    GraphEdgeView,
    GraphNodeView,
    GraphRetrieval,
    RetrievalGraph,
    RetrievalKind,
    RetrievalRequest,
    RetrievalService,
    TrustedRetrievalContext,
    VectorDocument,
    assert_model_arguments_trusted_free,
    bound_limit,
    redact_graph,
    redact_mapping,
)
from src.shared import auth
from tests.unit_tests.fixtures import gateway_headers, get_async_test_client


@pytest.mark.parametrize(
    "delegated_user", [None, "", "   ", "internal-service", "dev-user"]
)
async def test_internal_retrieval_rejects_missing_or_reserved_user(
    monkeypatch, delegated_user
):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")
    authorize = AsyncMock(return_value=AuthorizedCollection("private", None))
    search = AsyncMock(return_value=())
    monkeypatch.setattr(retrieval, "authorize_collection_read", authorize)
    monkeypatch.setattr(retrieval, "search_collection_vectors", search)
    headers = {"X-Internal-Service-Token": "internal-token"}
    if delegated_user is not None:
        headers["x-user-id"] = delegated_user
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "private"},
            headers=headers,
        )
    assert response.status_code == 403
    authorize.assert_not_awaited()
    search.assert_not_awaited()


@pytest.mark.parametrize(
    "token_header", ["X-Internal-Service-Token", "x-internal-token"]
)
async def test_internal_retrieval_accepts_each_token_header_with_delegation(
    monkeypatch, token_header
):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")
    authorize = AsyncMock(return_value=AuthorizedCollection("shared", None))
    search = AsyncMock(return_value=())
    monkeypatch.setattr(retrieval, "authorize_collection_read", authorize)
    monkeypatch.setattr(retrieval, "search_collection_vectors", search)
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "shared"},
            headers={token_header: "internal-token", "x-user-id": "member"},
        )
    assert response.status_code == 200
    authorize.assert_awaited_once_with("member", "shared")


async def _allow(user_id: str, collection_id: str) -> AuthorizedCollection:
    return AuthorizedCollection(identifier=collection_id, name="HR Policies")


async def _deny(user_id: str, collection_id: str) -> AuthorizedCollection | None:
    return None


async def _vector(query: str, *, limit: int) -> tuple[VectorDocument, ...]:
    return (
        VectorDocument(
            identifier="doc-1",
            content=f"vector:{query}",
            score=0.9,
            metadata={"token": "secret", "source": "milvus"},
        ),
    )[:limit]


async def _graph(query: str, *, limit: int) -> GraphRetrieval:
    return GraphRetrieval(
        nodes=(
            GraphNodeView(
                identifier="node-1",
                name=f"graph:{query}",
                label="Concept",
                matched=True,
                score=0.8,
                properties={"password": "secret", "since": 2024},
            ),
            GraphNodeView(
                identifier="node-2",
                name="Line Manager",
                label="Role",
                matched=False,
                score=None,
                properties={},
            ),
        )[:limit],
        edges=(
            GraphEdgeView(
                identifier="edge-1",
                source="node-1",
                target="node-2",
                type="REQUIRES_APPROVAL_FROM",
                properties={},
            ),
        ),
        context="Knowledge Graph Context",
        score=0.8,
    )


async def _vector_many(query: str, *, limit: int) -> tuple[VectorDocument, ...]:
    return tuple(
        VectorDocument(
            identifier=f"doc-{index}",
            content=f"vector-{index}:{query}",
            score=0.9 - (index * 0.1),
            metadata={},
        )
        for index in range(limit)
    )


def test_assert_model_arguments_trusted_free_ok() -> None:
    assert_model_arguments_trusted_free({"query": "hello"})


def test_assert_model_arguments_trusted_free_rejects_reserved_key() -> None:
    with pytest.raises(ValidationFailedError) as exc_info:
        assert_model_arguments_trusted_free({"trusted_context": "forged"})
    assert exc_info.value.code == "forbidden_trusted_field"


def test_assert_model_arguments_trusted_free_rejects_nested_reserved_key() -> None:
    with pytest.raises(ValidationFailedError) as exc_info:
        assert_model_arguments_trusted_free(
            {"params": {"arguments": {"user_id": "evil"}}}
        )
    assert exc_info.value.code == "forbidden_trusted_field"


def test_redact_mapping_masks_secrets() -> None:
    redacted = redact_mapping({"token": "abc", "title": "ok"})
    assert redacted["token"] == "***REDACTED***"
    assert redacted["title"] == "ok"


def test_bound_limit_clamps() -> None:
    assert bound_limit(0) == 1
    assert bound_limit(3) == 3
    assert bound_limit(MAX_LIMIT + 10) == MAX_LIMIT


@pytest.mark.asyncio
async def test_vector_retrieval_redacts_and_authorizes() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="  tariffs  ",
            collection_id=" col-1 ",
            kind=RetrievalKind.VECTOR,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.kind is RetrievalKind.VECTOR
    assert result.collection_id == "col-1"
    assert result.hits[0].content == "vector:tariffs"
    assert result.hits[0].metadata["token"] == "***REDACTED***"
    assert result.hits[0].source == "vector"


@pytest.mark.asyncio
async def test_graph_retrieval_returns_context() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="entity",
            collection_id="col-1",
            kind=RetrievalKind.GRAPH,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.hits[0].source == "graph"
    assert result.context == "Knowledge Graph Context"


@pytest.mark.asyncio
async def test_hybrid_retrieval_combines_sources() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="mix",
            collection_id="col-1",
            kind=RetrievalKind.HYBRID,
            limit=10,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    sources = {hit.source for hit in result.hits}
    assert sources == {"vector", "graph"}


@pytest.mark.asyncio
async def test_hybrid_retrieval_keeps_graph_hit_when_vector_page_is_full() -> None:
    service = RetrievalService(
        vector_search=_vector_many,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="mix",
            collection_id="col-1",
            kind=RetrievalKind.HYBRID,
            limit=2,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    sources = [hit.source for hit in result.hits]
    assert sources == ["vector", "graph"]


@pytest.mark.asyncio
async def test_denied_collection_raises_forbidden() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_deny,
    )
    with pytest.raises(ForbiddenError):
        await service.retrieve(
            RetrievalRequest(
                query="q",
                collection_id="col-1",
                trusted_context=TrustedRetrievalContext(user_id="user-1"),
            )
        )


@pytest.mark.asyncio
async def test_missing_trusted_user_raises_forbidden() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    with pytest.raises(ForbiddenError):
        await service.retrieve(RetrievalRequest(query="q", collection_id="col-1"))


@pytest.mark.asyncio
async def test_retrieval_route_requires_auth() -> None:
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "col-1"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_retrieval_route_rejects_trusted_fields_in_body() -> None:
    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={
                "query": "q",
                "collection_id": "col-1",
                "trusted_context": {"user_id": "forged"},
            },
            headers=gateway_headers("user1"),
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieval_route_uses_trusted_header_user_for_internal_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")
    captured: dict[str, str] = {}

    async def fake_vector(
        collection_id: str, user_id: str, query: str, *, limit: int
    ) -> tuple[VectorDocument, ...]:
        captured["collection_id"] = collection_id
        captured["user_id"] = user_id
        captured["query"] = query
        return ()

    async def fake_authorize(user_id: str, collection_id: str) -> AuthorizedCollection:
        captured["authorized_user_id"] = user_id
        captured["authorized_collection_id"] = collection_id
        return AuthorizedCollection(identifier=collection_id, name=None)

    monkeypatch.setattr(retrieval, "search_collection_vectors", fake_vector)
    monkeypatch.setattr(retrieval, "authorize_collection_read", fake_authorize)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "col-1", "kind": "vector"},
            headers={
                "X-Internal-Service-Token": "internal-token",
                "x-internal-token": "internal-token",
                "x-user-id": "trusted-user",
                "x-tenant-id": "tenant-1",
            },
        )

    assert response.status_code == 200
    assert captured["user_id"] == "trusted-user"
    assert captured["authorized_user_id"] == "trusted-user"


@pytest.mark.asyncio
async def test_retrieval_route_ignores_trusted_headers_for_public_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_vector(
        collection_id: str, user_id: str, query: str, *, limit: int
    ) -> tuple[VectorDocument, ...]:
        captured["user_id"] = user_id
        return ()

    async def fake_authorize(user_id: str, collection_id: str) -> AuthorizedCollection:
        captured["authorized_user_id"] = user_id
        return AuthorizedCollection(identifier=collection_id, name=None)

    monkeypatch.setattr(retrieval, "search_collection_vectors", fake_vector)
    monkeypatch.setattr(retrieval, "authorize_collection_read", fake_authorize)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "col-1", "kind": "vector"},
            headers={
                **gateway_headers("user1"),
                # A bogus internal token and a spoofed delegation header must
                # neither authenticate the caller as the service nor make the
                # caller someone else.
                "x-internal-token": "bogus",
                "x-user-id": "victim-user",
            },
        )

    assert response.status_code == 200
    assert captured["user_id"] == "user1"
    assert captured["authorized_user_id"] == "user1"


@pytest.mark.asyncio
async def test_retrieval_route_requires_graph_permission_for_hybrid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")

    async def deny_graph_permission(user_id: str, access_token: str | None) -> bool:
        return False

    monkeypatch.setattr(retrieval, "has_graph_search_permission", deny_graph_permission)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "col-1", "kind": "hybrid"},
            headers={
                "X-Internal-Service-Token": "internal-token",
                "x-internal-token": "internal-token",
                "x-user-id": "trusted-user",
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_empty_query_raises_validation_error() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    with pytest.raises(ValidationFailedError):
        await service.retrieve(
            RetrievalRequest(
                query="   ",
                collection_id="col-1",
                trusted_context=TrustedRetrievalContext(user_id="user-1"),
            )
        )


async def test_vector_retrieval_builds_numbered_context() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="tariffs",
            collection_id="col-1",
            kind=RetrievalKind.VECTOR,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.context == "[1] (milvus)\nvector:tariffs"


async def test_retrieval_reports_collection_name() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="q",
            collection_id="col-1",
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.collection_name == "HR Policies"


async def test_graph_retrieval_returns_redacted_subgraph() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="leave",
            collection_id="col-1",
            kind=RetrievalKind.GRAPH,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.graph is not None
    assert [(node.identifier, node.matched) for node in result.graph.nodes] == [
        ("node-1", True),
        ("node-2", False),
    ]
    assert result.graph.nodes[0].properties["password"] == "***REDACTED***"
    assert [edge.type for edge in result.graph.edges] == ["REQUIRES_APPROVAL_FROM"]
    assert [hit.content for hit in result.hits] == ["graph:leave", "Line Manager"]


async def test_vector_retrieval_has_no_graph() -> None:
    service = RetrievalService(
        vector_search=_vector,
        graph_search=_graph,
        authorize=_allow,
    )
    result = await service.retrieve(
        RetrievalRequest(
            query="q",
            collection_id="col-1",
            kind=RetrievalKind.VECTOR,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        )
    )
    assert result.graph is None


async def test_retrieval_route_returns_collection_name_and_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")

    async def fake_graph(
        collection_id: str, user_id: str, query: str, *, limit: int
    ) -> GraphRetrieval:
        return await _graph(query, limit=limit)

    async def allow_graph_permission(user_id: str, access_token: str | None) -> bool:
        return True

    monkeypatch.setattr(retrieval, "search_collection_graph", fake_graph)
    monkeypatch.setattr(retrieval, "authorize_collection_read", _allow)
    monkeypatch.setattr(
        retrieval, "has_graph_search_permission", allow_graph_permission
    )

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "leave", "collection_id": "col-1", "kind": "graph"},
            headers={
                "X-Internal-Service-Token": "internal-token",
                "x-user-id": "trusted-user",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["collection_name"] == "HR Policies"
    assert body["graph"]["nodes"][0] == {
        "id": "node-1",
        "name": "graph:leave",
        "label": "Concept",
        "matched": True,
        "score": 0.8,
        "properties": {"password": "***REDACTED***", "since": 2024},
    }
    assert body["graph"]["edges"][0]["type"] == "REQUIRES_APPROVAL_FROM"


async def test_retrieve_authorized_skips_the_authorize_port() -> None:
    service = RetrievalService(vector_search=_vector, graph_search=_graph)
    result = await service.retrieve_authorized(
        RetrievalRequest(
            query="q",
            collection_id="col-1",
            kind=RetrievalKind.VECTOR,
            trusted_context=TrustedRetrievalContext(user_id="user-1"),
        ),
        AuthorizedCollection("col-1", "Vetted"),
    )
    assert result.collection_name == "Vetted"
    assert result.hits[0].metadata["token"] == "***REDACTED***"


async def test_retrieve_authorized_rejects_a_different_collection() -> None:
    service = RetrievalService(vector_search=_vector, graph_search=_graph)
    with pytest.raises(ForbiddenError):
        await service.retrieve_authorized(
            RetrievalRequest(
                query="q",
                collection_id="other",
                trusted_context=TrustedRetrievalContext(user_id="user-1"),
            ),
            AuthorizedCollection("col-1", "Vetted"),
        )


async def test_retrieve_authorized_still_requires_a_trusted_user() -> None:
    service = RetrievalService(vector_search=_vector, graph_search=_graph)
    with pytest.raises(ForbiddenError):
        await service.retrieve_authorized(
            RetrievalRequest(query="q", collection_id="col-1"),
            AuthorizedCollection("col-1", None),
        )


async def test_retrieve_without_authorize_port_is_a_programming_error() -> None:
    service = RetrievalService(vector_search=_vector, graph_search=_graph)
    with pytest.raises(RuntimeError):
        await service.retrieve(
            RetrievalRequest(
                query="q",
                collection_id="col-1",
                trusted_context=TrustedRetrievalContext(user_id="user-1"),
            )
        )


def test_redact_graph_masks_node_and_edge_properties() -> None:
    graph = RetrievalGraph(
        nodes=(GraphNodeView("a", "A", "Role", True, 0.5, {"password": "x", "ok": 1}),),
        edges=(GraphEdgeView("e", "a", "a", "SELF", {"api_key": "k"}),),
    )
    redacted = redact_graph(graph)
    assert redacted.nodes[0].properties == {"password": "***REDACTED***", "ok": 1}
    assert redacted.edges[0].properties == {"api_key": "***REDACTED***"}
