from __future__ import annotations

import pytest
from error_contract import ForbiddenError, ValidationFailedError

from langconnect import auth
from langconnect.api import retrieval
from langconnect.services.retrieval_contract import (
    MAX_LIMIT,
    GraphDocument,
    RetrievalKind,
    RetrievalRequest,
    RetrievalService,
    TrustedRetrievalContext,
    VectorDocument,
    assert_model_arguments_trusted_free,
    bound_limit,
    redact_mapping,
)
from tests.unit_tests.fixtures import get_async_test_client


async def _allow(user_id: str, collection_id: str) -> bool:
    return True


async def _deny(user_id: str, collection_id: str) -> bool:
    return False


async def _vector(query: str, *, limit: int) -> tuple[VectorDocument, ...]:
    return (
        VectorDocument(
            identifier="doc-1",
            content=f"vector:{query}",
            score=0.9,
            metadata={"token": "secret", "source": "milvus"},
        ),
    )[:limit]


async def _graph(query: str, *, limit: int) -> tuple[GraphDocument, ...]:
    return (
        GraphDocument(
            identifier="node-1",
            content=f"graph:{query}",
            score=0.8,
            context="Knowledge Graph Context",
            metadata={"label": "Concept"},
        ),
    )[:limit]


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
            headers={"Authorization": "Bearer user1"},
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

    async def fake_authorize(user_id: str, collection_id: str) -> bool:
        captured["authorized_user_id"] = user_id
        captured["authorized_collection_id"] = collection_id
        return True

    monkeypatch.setattr(retrieval, "_vector_search", fake_vector)
    monkeypatch.setattr(retrieval, "_authorize", fake_authorize)

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

    async def fake_authorize(user_id: str, collection_id: str) -> bool:
        captured["authorized_user_id"] = user_id
        return True

    monkeypatch.setattr(retrieval, "_vector_search", fake_vector)
    monkeypatch.setattr(retrieval, "_authorize", fake_authorize)

    async with get_async_test_client() as client:
        response = await client.post(
            "/api/v1/retrieval",
            json={"query": "q", "collection_id": "col-1", "kind": "vector"},
            headers={
                "Authorization": "Bearer user1",
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

    monkeypatch.setattr(
        retrieval, "_has_graph_search_permission", deny_graph_permission
    )

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
