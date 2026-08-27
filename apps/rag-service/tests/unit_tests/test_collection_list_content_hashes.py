import pytest

from langconnect.services.collections import Collection


class FakeMilvusCollection:
    """Minimal Milvus collection double for query()-based reads."""

    def __init__(self, rows: list[dict]) -> None:
        """Seed the rows to be returned by query()."""
        self._rows = rows

    def query(self, **kwargs: object) -> list[dict]:
        """Return the seeded rows."""
        return self._rows


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names."""

    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(self, rows: list[dict]) -> None:
        """Wrap a FakeMilvusCollection seeded with the given rows."""
        self.col = FakeMilvusCollection(rows)


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_list_content_hashes_returns_unique_hashes(monkeypatch) -> None:
    store = FakeVectorStore(
        rows=[
            {"pk": 1, "text": "chunk 1", "metadata": {"content_hash": "hash-a"}},
            {"pk": 2, "text": "chunk 2", "metadata": {"content_hash": "hash-a"}},
            {"pk": 3, "text": "chunk 3", "metadata": {"content_hash": "hash-b"}},
        ]
    )
    collection = await _make_collection(monkeypatch, store)

    hashes = await collection.list_content_hashes()

    assert hashes == {"hash-a", "hash-b"}


@pytest.mark.asyncio
async def test_list_content_hashes_ignores_rows_without_hash(monkeypatch) -> None:
    store = FakeVectorStore(
        rows=[
            {"pk": 1, "text": "chunk 1", "metadata": {}},
            {"pk": 2, "text": "chunk 2", "metadata": {"content_hash": "hash-b"}},
        ]
    )
    collection = await _make_collection(monkeypatch, store)

    hashes = await collection.list_content_hashes()

    assert hashes == {"hash-b"}


@pytest.mark.asyncio
async def test_list_content_hashes_empty_when_no_store_collection(monkeypatch) -> None:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details():
        return {"table_id": "milvus-table"}

    class EmptyStore:
        col = None

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: EmptyStore())

    hashes = await collection.list_content_hashes()

    assert hashes == set()
