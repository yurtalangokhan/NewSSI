import pytest

from src.documents.service import Collection


class FakeMilvusIterator:
    """Minimal pymilvus query iterator double."""

    def __init__(self, batches: list[list[dict]]) -> None:
        """Initialize with precomputed query batches."""
        self._batches = batches
        self.closed = False

    def next(self) -> list[dict]:
        """Return the next batch, matching pymilvus iterator semantics."""
        if self._batches:
            return self._batches.pop(0)
        return []

    def close(self) -> None:
        """Mark the iterator as closed."""
        self.closed = True


class FakeMilvusCollection:
    """Minimal Milvus collection double with iterator support."""

    def __init__(self) -> None:
        """Initialize query call tracking."""
        self.iterator: FakeMilvusIterator | None = None
        self.batch_size: int | None = None
        self.limit: int | None = None
        self.consistency_level: str | None = None

    def query(self, **kwargs: object) -> list[dict]:
        """Fail when legacy code asks for too large a query window."""
        limit = kwargs.get("limit", 0)
        if isinstance(limit, int) and limit > 16_384:
            raise AssertionError("Milvus query limit exceeds max result window")
        self.consistency_level = kwargs.get("consistency_level")
        return []

    def query_iterator(self, **kwargs: object) -> FakeMilvusIterator:
        """Return a fake iterator and capture iterator options."""
        self.batch_size = kwargs.get("batch_size")
        self.limit = kwargs.get("limit")
        self.consistency_level = kwargs.get("consistency_level")
        self.iterator = FakeMilvusIterator(
            [
                [
                    {"pk": 1, "text": "first", "metadata": {"file_id": "a"}},
                    {"pk": 2, "text": "second", "metadata": {"file_id": "b"}},
                ],
                [{"pk": 3, "text": "third", "metadata": {"file_id": "c"}}],
            ]
        )
        return self.iterator


class FakeMilvusCollectionWithoutIterator:
    """Milvus collection double for pymilvus builds lacking query_iterator()."""

    def __init__(self) -> None:
        """Initialize query call tracking."""
        self.consistency_level: str | None = None

    def query(self, **kwargs: object) -> list[dict]:
        """Record the consistency level requested by the caller."""
        self.consistency_level = kwargs.get("consistency_level")
        return [{"pk": 1, "text": "first", "metadata": {"file_id": "a"}}]


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names."""

    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(self) -> None:
        """Initialize the fake Milvus collection."""
        self.col = FakeMilvusCollection()


@pytest.mark.asyncio
async def test_fetch_all_chunks_uses_milvus_iterator(monkeypatch) -> None:
    collection = Collection(collection_id="collection-id", user_id="user-id")
    store = FakeVectorStore()

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)

    chunks = await collection.fetch_all_chunks()

    assert chunks == [
        {"id": "1", "content": "first", "metadata": {"file_id": "a"}},
        {"id": "2", "content": "second", "metadata": {"file_id": "b"}},
        {"id": "3", "content": "third", "metadata": {"file_id": "c"}},
    ]
    assert store.col.batch_size is not None
    assert store.col.batch_size <= 16_384
    assert store.col.limit == -1
    assert store.col.iterator is not None
    assert store.col.iterator.closed is True
    assert store.col.consistency_level == "Strong"


@pytest.mark.asyncio
async def test_fetch_all_chunks_requests_strong_consistency_without_iterator(
    monkeypatch,
) -> None:
    """Milvus only guarantees a query sees prior writes when it isn't left to
    eventual consistency. upsert() no longer flushes after every batch, so
    reads that must see just-written rows (e.g. the duplicate-filename check
    before a new upload) ask Milvus directly via consistency_level="Strong"
    instead.
    """
    collection = Collection(collection_id="collection-id", user_id="user-id")
    store = FakeVectorStore()
    store.col = FakeMilvusCollectionWithoutIterator()

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)

    chunks = await collection.fetch_all_chunks()

    assert chunks == [{"id": "1", "content": "first", "metadata": {"file_id": "a"}}]
    assert store.col.consistency_level == "Strong"
