import pytest

from langconnect.services.collections import Collection


class FakeMilvusCollection:
    """Minimal Milvus collection double recording query() kwargs."""

    def __init__(self, rows_by_call: list[list[dict]]) -> None:
        """Queue up the rows to return for each successive query() call."""
        self._rows_by_call = list(rows_by_call)
        self.calls: list[dict] = []

    def query(self, **kwargs: object) -> list[dict]:
        """Record kwargs and pop the next queued row batch."""
        self.calls.append(kwargs)
        if self._rows_by_call:
            return self._rows_by_call.pop(0)
        return []


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names."""

    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(self, rows_by_call: list[list[dict]]) -> None:
        """Wrap a FakeMilvusCollection seeded with per-call row batches."""
        self.col = FakeMilvusCollection(rows_by_call)


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_get_chunks_passes_limit_and_offset_to_milvus(monkeypatch) -> None:
    store = FakeVectorStore(
        rows_by_call=[
            [{"pk": 3, "text": "third", "metadata": {"file_id": "f1"}}],
        ]
    )
    collection = await _make_collection(monkeypatch, store)

    chunks = await collection.get_chunks(file_id="f1", limit=1, offset=2)

    assert chunks == [{"id": "3", "content": "third", "metadata": {"file_id": "f1"}}]
    assert store.col.calls[0]["limit"] == 1
    assert store.col.calls[0]["offset"] == 2


@pytest.mark.asyncio
async def test_get_chunk_stats_uses_single_row_when_totals_precomputed(
    monkeypatch,
) -> None:
    store = FakeVectorStore(
        rows_by_call=[
            [
                {
                    "pk": 1,
                    "text": "first",
                    "metadata": {
                        "file_id": "f1",
                        "file_total_chunks": 42,
                        "file_avg_chars": 100,
                        "file_avg_tokens": 25,
                    },
                }
            ],
        ]
    )
    collection = await _make_collection(monkeypatch, store)

    stats = await collection.get_chunk_stats(file_id="f1")

    assert stats == {"total_chunks": 42, "avg_chars": 100, "avg_tokens": 25}
    # Only the single-row lookup was needed — no full-collection fetch.
    assert len(store.col.calls) == 1
    assert store.col.calls[0]["limit"] == 1


@pytest.mark.asyncio
async def test_get_chunk_stats_falls_back_to_full_scan_for_legacy_chunks(
    monkeypatch,
) -> None:
    store = FakeVectorStore(
        rows_by_call=[
            # First call: single-row lookup, no precomputed stats (legacy chunk).
            [{"pk": 1, "text": "first chunk", "metadata": {"file_id": "f1"}}],
            # Second call: full scan fallback to compute real averages.
            [
                {"pk": 1, "text": "abcd", "metadata": {"file_id": "f1"}},
                {"pk": 2, "text": "ab", "metadata": {"file_id": "f1"}},
            ],
        ]
    )
    collection = await _make_collection(monkeypatch, store)

    stats = await collection.get_chunk_stats(file_id="f1")

    assert stats["total_chunks"] == 2
    assert stats["avg_chars"] == 3  # (4 + 2) / 2
    assert len(store.col.calls) == 2


@pytest.mark.asyncio
async def test_get_chunk_stats_empty_when_no_chunks(monkeypatch) -> None:
    store = FakeVectorStore(rows_by_call=[[]])
    collection = await _make_collection(monkeypatch, store)

    stats = await collection.get_chunk_stats(file_id="missing")

    assert stats == {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}
