"""``Collection.list`` must page documents without pulling the whole corpus.

Deduplicating one representative chunk per file_id needs every row scanned
(Milvus has no GROUP BY), but only the returned page needs its text. The
scan therefore asks for ids + metadata only, and a second targeted query
fetches text for just that page's rows.
"""

import pytest
from error_contract import DatabaseOperationError
from pymilvus.exceptions import MilvusException

from src.documents.service import Collection


class FakeMilvusIterator:
    """Minimal pymilvus query iterator double."""

    def __init__(self, batches: list[list[dict]]) -> None:
        """Initialize with precomputed query batches."""
        self._batches = [list(b) for b in batches]
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
    """Milvus double recording scan output_fields and targeted text queries."""

    def __init__(self, rows: list[dict]) -> None:
        """Seed the rows the collection holds."""
        self._rows = rows
        self.scan_output_fields: list[str] | None = None
        self.query_calls: list[dict] = []

    def query_iterator(self, **kwargs: object) -> FakeMilvusIterator:
        """Serve the full scan, recording which fields it asked for."""
        self.scan_output_fields = list(kwargs.get("output_fields") or [])
        projected = [
            {k: v for k, v in row.items() if k in self.scan_output_fields}
            for row in self._rows
        ]
        return FakeMilvusIterator([projected])

    def query(self, **kwargs: object) -> list[dict]:
        """Serve the targeted text fetch for a page's primary keys."""
        self.query_calls.append(kwargs)
        expr = str(kwargs.get("expr", ""))
        wanted = {
            int(part.strip())
            for part in expr.partition("[")[2].partition("]")[0].split(",")
            if part.strip()
        }
        fields = list(kwargs.get("output_fields") or [])
        return [
            {k: v for k, v in row.items() if k in fields}
            for row in self._rows
            if row["pk"] in wanted
        ]


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names."""

    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(self, rows: list[dict]) -> None:
        """Wrap a FakeMilvusCollection seeded with rows."""
        self.col = FakeMilvusCollection(rows)


ROWS = [
    {"pk": 1, "text": "alpha one", "metadata": {"file_id": "a"}},
    {"pk": 2, "text": "alpha two", "metadata": {"file_id": "a"}},
    {"pk": 3, "text": "bravo one", "metadata": {"file_id": "b"}},
    {"pk": 4, "text": "charlie one", "metadata": {"file_id": "c"}},
]


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details(required_permission="read"):
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_list_returns_one_document_per_file_id(monkeypatch) -> None:
    store = FakeVectorStore(ROWS)
    collection = await _make_collection(monkeypatch, store)

    docs = await collection.list(limit=10, offset=0)

    assert [d["id"] for d in docs] == ["a", "b", "c"]
    assert [d["content"] for d in docs] == ["alpha one", "bravo one", "charlie one"]
    assert all(d["collection_id"] == "collection-id" for d in docs)


@pytest.mark.asyncio
async def test_list_scan_does_not_request_chunk_text(monkeypatch) -> None:
    """The whole point of the two-phase fetch: the full scan must not drag
    every chunk's text back with it.
    """
    store = FakeVectorStore(ROWS)
    collection = await _make_collection(monkeypatch, store)

    await collection.list(limit=1, offset=0)

    assert store.col.scan_output_fields == ["pk", "metadata"]
    assert "text" not in store.col.scan_output_fields


@pytest.mark.asyncio
async def test_list_fetches_text_only_for_the_requested_page(monkeypatch) -> None:
    store = FakeVectorStore(ROWS)
    collection = await _make_collection(monkeypatch, store)

    docs = await collection.list(limit=1, offset=1)

    assert [d["id"] for d in docs] == ["b"]
    assert docs[0]["content"] == "bravo one"
    # Exactly one targeted fetch, scoped to that single page row.
    assert len(store.col.query_calls) == 1
    assert store.col.query_calls[0]["expr"] == "pk in [3]"


@pytest.mark.asyncio
async def test_list_returns_no_leaked_internal_keys(monkeypatch) -> None:
    store = FakeVectorStore(ROWS)
    collection = await _make_collection(monkeypatch, store)

    docs = await collection.list(limit=10, offset=0)

    for doc in docs:
        assert set(doc) == {"id", "content", "metadata", "collection_id"}


@pytest.mark.asyncio
async def test_list_is_empty_past_the_last_page(monkeypatch) -> None:
    store = FakeVectorStore(ROWS)
    collection = await _make_collection(monkeypatch, store)

    assert await collection.list(limit=10, offset=99) == []
    # Nothing to fetch text for, so no second query at all.
    assert store.col.query_calls == []


@pytest.mark.asyncio
async def test_list_does_not_hide_a_failed_text_fetch(monkeypatch) -> None:
    """A text fetch that fails is a backend failure, not an empty document: it
    surfaces as a typed database error instead of blank content that looks like
    a successful listing.
    """
    store = FakeVectorStore(ROWS)

    def boom(**kwargs: object):
        raise MilvusException(message="milvus unavailable")

    store.col.query = boom  # type: ignore[method-assign]
    collection = await _make_collection(monkeypatch, store)

    with pytest.raises(DatabaseOperationError):
        await collection.list(limit=10, offset=0)
