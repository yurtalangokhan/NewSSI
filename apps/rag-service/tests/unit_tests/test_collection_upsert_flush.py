import pytest

from langconnect.database.collections import Collection


class FakeMilvusCollection:
    """Minimal pymilvus Collection double tracking flush() calls."""

    def __init__(self) -> None:
        """Track whether flush() was called."""
        self.flush_called = False

    def flush(self) -> None:
        """Mark that a flush occurred."""
        self.flush_called = True


class FakeVectorStore:
    """Minimal vector store double exposing add_documents() and .col."""

    def __init__(self, ids: list[str]) -> None:
        """Seed the ids returned by add_documents()."""
        self._ids = ids
        self.col = FakeMilvusCollection()
        self.add_documents_calls: list[list] = []

    def add_documents(self, documents: list) -> list[str]:
        """Record the call and return the seeded ids."""
        self.add_documents_calls.append(documents)
        return self._ids


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_upsert_flushes_after_add_documents_so_reads_see_new_rows(
    monkeypatch,
) -> None:
    """A dedup check issued right after upsert() must see the just-added rows.

    Milvus doesn't guarantee a just-inserted row is visible to a later query
    from a different request unless the collection is flushed, which is
    exactly the read-after-write gap the duplicate-filename check depends on.
    """
    store = FakeVectorStore(ids=["1", "2"])
    collection = await _make_collection(monkeypatch, store)

    await collection.upsert([object(), object()])

    assert store.col.flush_called is True


@pytest.mark.asyncio
async def test_upsert_returns_string_ids(monkeypatch) -> None:
    store = FakeVectorStore(ids=[1, 2])
    collection = await _make_collection(monkeypatch, store)

    ids = await collection.upsert([object(), object()])

    assert ids == ["1", "2"]
