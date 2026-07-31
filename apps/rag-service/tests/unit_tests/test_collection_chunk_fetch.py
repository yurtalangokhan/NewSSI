import pytest

from langconnect.database.collections import Collection


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

    def query(self, **kwargs: object) -> list[dict]:
        """Fail when legacy code asks for too large a query window."""
        limit = kwargs.get("limit", 0)
        if isinstance(limit, int) and limit > 16_384:
            raise AssertionError("Milvus query limit exceeds max result window")
        return []

    def query_iterator(self, **kwargs: object) -> FakeMilvusIterator:
        """Return a fake iterator and capture iterator options."""
        self.batch_size = kwargs.get("batch_size")
        self.limit = kwargs.get("limit")
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
