"""Deciding what is a duplicate must not read the collection twice.

Before embedding anything, an upload job asks the collection which
filenames and which content hashes it already holds. Both answers come from
the same field of the same rows -- every chunk's metadata -- but they were
two separate calls, so each job streamed the entire collection end to end
twice before the first file was even looked at. On a collection of any size
that is the dominant cost of the job, and it is paid per job, not per file.

One pass answers both.
"""

from __future__ import annotations

import pytest
from error_contract import DatabaseConnectionError
from pymilvus.exceptions import MilvusUnavailableException

from src.documents.service import Collection


class _FakeMilvusCollection:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.query_calls = 0

    def query(self, **kwargs: object) -> list[dict]:
        self.query_calls += 1
        return self._rows


class _FakeVectorStore:
    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(self, rows: list[dict]) -> None:
        self.col = _FakeMilvusCollection(rows)


def _rows() -> list[dict]:
    return [
        {
            "pk": 1,
            "text": "c1",
            "metadata": {"filename": "a.pdf", "content_hash": "aaa"},
        },
        {
            "pk": 2,
            "text": "c2",
            "metadata": {"filename": "a.pdf", "content_hash": "aaa"},
        },
        {
            "pk": 3,
            "text": "c3",
            "metadata": {"filename": "b.pdf", "content_hash": "bbb"},
        },
        {"pk": 4, "text": "c4", "metadata": {}},
    ]


async def _collection(monkeypatch, store: _FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="user-id")

    async def fake_details():
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_both_fingerprint_sets_come_from_one_scan(monkeypatch) -> None:
    store = _FakeVectorStore(_rows())
    collection = await _collection(monkeypatch, store)

    filenames, hashes = await collection.list_upload_fingerprints()

    assert filenames == {"a.pdf", "b.pdf"}
    assert hashes == {"aaa", "bbb"}
    assert store.col.query_calls == 1, (
        f"read the collection {store.col.query_calls} times to answer one "
        "duplicate check"
    )


@pytest.mark.asyncio
async def test_an_unreadable_collection_reports_a_typed_storage_failure(monkeypatch) -> None:
    """A failed scan must remain distinguishable from an empty collection."""
    store = _FakeVectorStore(_rows())

    def explode(**_kwargs: object):
        raise MilvusUnavailableException(message="milvus is down")

    store.col.query = explode
    collection = await _collection(monkeypatch, store)

    with pytest.raises(DatabaseConnectionError):
        await collection.list_upload_fingerprints()


@pytest.mark.asyncio
async def test_a_collection_with_no_store_reports_nothing_seen(monkeypatch) -> None:
    store = _FakeVectorStore([])
    store.col = None
    collection = await _collection(monkeypatch, store)

    assert await collection.list_upload_fingerprints() == (set(), set())


@pytest.mark.asyncio
async def test_the_upload_job_asks_once_for_both(monkeypatch) -> None:
    """The caller uses the single-pass call, not the two it replaced."""
    from src.documents import upload_service as document_upload_service

    calls: list[str] = []

    class _Collection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def list_upload_fingerprints(self) -> tuple[set[str], set[str]]:
            calls.append("fingerprints")
            return {"already.pdf"}, {"deadbeef"}

        async def upsert(self, _batch: object) -> list[str]:
            raise AssertionError("no file should have been embedded")

    monkeypatch.setattr(document_upload_service, "Collection", _Collection)
    document_upload_service.initialize_upload_progress("collection-id", total_files=0)

    await document_upload_service.run_upload_job(
        collection_id="collection-id",
        user_id="user-id",
        files=[],
        metadatas=[],
    )

    assert calls == ["fingerprints"]
