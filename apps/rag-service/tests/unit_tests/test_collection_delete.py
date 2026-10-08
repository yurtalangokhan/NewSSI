"""``Collection.delete`` must surface a real Milvus failure, not mask it as success.

It used to catch every exception, log it, and unconditionally return
``True`` -- a backend outage during a document delete request looked
identical to a successful delete from the caller's side, and the route
even had 404-vs-success logic that could never fire.
"""

import pytest
from error_contract import DependencyUnavailableError
from pymilvus.exceptions import MilvusUnavailableException

from src.documents.service import Collection


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names.

    ``Collection.delete`` calls ``store.delete(...)`` directly -- that's a
    method on LangChain's Milvus vectorstore wrapper itself, not on the
    underlying pymilvus ``store.col``.
    """

    _metadata_field = "metadata"

    def __init__(self, *, fail: bool = False) -> None:
        """Configure whether delete() raises."""
        self._fail = fail
        self.delete_calls: list[str] = []

    def delete(self, expr: str) -> None:
        """Record the call and optionally raise, matching a Milvus failure."""
        self.delete_calls.append(expr)
        if self._fail:
            raise MilvusUnavailableException("milvus unavailable")


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details(required_permission="read"):
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_delete_succeeds_silently_when_milvus_call_succeeds(monkeypatch) -> None:
    store = FakeVectorStore(fail=False)
    collection = await _make_collection(monkeypatch, store)

    await collection.delete(file_id="doc-1")  # must not raise

    assert store.delete_calls


@pytest.mark.asyncio
async def test_delete_raises_dependency_unavailable_on_milvus_failure(monkeypatch) -> None:
    store = FakeVectorStore(fail=True)
    collection = await _make_collection(monkeypatch, store)

    with pytest.raises(DependencyUnavailableError) as excinfo:
        await collection.delete(file_id="doc-1")

    assert excinfo.value.status_code == 503
    # The driver diagnostic stays in the exception chain, out of the public body.
    assert isinstance(excinfo.value.__cause__, MilvusUnavailableException)
