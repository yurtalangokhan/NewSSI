import pytest

from src.documents.service import Collection


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

    async def fake_details(required_permission="read"):
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_upsert_does_not_flush_after_every_batch(monkeypatch) -> None:
    """flush() forces a segment seal -- real work, paid on every single batch
    an upload job writes, whether or not anything reads the collection again
    soon after.

    A dedup check issued right after upsert() still needs to see the
    just-added rows, but that guarantee now belongs to the *read* --
    _fetch_milvus_rows asks Milvus for consistency_level="Strong", which is
    the mechanism Milvus documents for exactly this "see all completed
    writes" requirement (see test_collection_chunk_fetch.py). That moves the
    cost from every write to only the reads that actually need it, instead
    of paying it unconditionally on the write side.
    """
    store = FakeVectorStore(ids=["1", "2"])
    collection = await _make_collection(monkeypatch, store)

    await collection.upsert([object(), object()])

    assert store.col.flush_called is False


@pytest.mark.asyncio
async def test_upsert_returns_string_ids(monkeypatch) -> None:
    store = FakeVectorStore(ids=[1, 2])
    collection = await _make_collection(monkeypatch, store)

    ids = await collection.upsert([object(), object()])

    assert ids == ["1", "2"]
