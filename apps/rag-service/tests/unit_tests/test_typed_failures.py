"""Regression coverage for storage and permission error boundaries."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from error_contract import DatabaseOperationError, DependencyTimeoutError
from pymilvus.exceptions import MilvusException

from src.documents.service import Collection
from src.graph.service import GraphRAGService
from src.shared.authorization import AuthorizationClient


async def test_permission_timeout_is_unavailable_not_denial(monkeypatch) -> None:
    service = AuthorizationClient()
    client = AsyncMock()
    client.post.side_effect = httpx.ReadTimeout("private upstream address")
    monkeypatch.setattr(
        "src.shared.authorization.get_shared_client", lambda name: client
    )
    with pytest.raises(DependencyTimeoutError):
        await service.check_collection_access("user", "collection")


async def test_milvus_failure_is_not_an_empty_collection(monkeypatch) -> None:
    collection = Collection("collection", "user")
    store = Mock()
    store.col.query_iterator.side_effect = MilvusException(message="private query")
    monkeypatch.setattr(
        collection,
        "_get_details_or_raise",
        AsyncMock(return_value={"table_id": "table"}),
    )
    monkeypatch.setattr(collection, "_get_store", Mock(return_value=store))
    with pytest.raises(DatabaseOperationError) as caught:
        await collection.list_upload_fingerprints()
    assert "private query" not in caught.value.message


async def test_vector_outage_is_not_graph_only_success(monkeypatch) -> None:
    monkeypatch.setattr(
        Collection, "search", AsyncMock(side_effect=DatabaseOperationError())
    )
    with pytest.raises(DatabaseOperationError):
        await GraphRAGService("collection")._vector_search("query")
