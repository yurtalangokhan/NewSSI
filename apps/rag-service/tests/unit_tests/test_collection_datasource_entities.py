"""Unit tests for the connector-managed (datasource) entity methods on Collection.

These back the ``/datasources/{id}/records`` and ``/datasources/{id}/entities``
endpoints used exclusively by agent-service's connector runtime --
never by the file-upload path, which groups chunks by file_id instead.
"""

from collections import OrderedDict
import logging

import pytest
from error_contract import DatabaseOperationError, DependencyUnavailableError
from langchain_core.documents import Document
from pymilvus.exceptions import MilvusException

from src.documents import service as documents_service
from src.documents.service import Collection
from src.shared import vectorstore

RECORD_KEY_A = "a" * 40
RECORD_KEY_B = "b" * 40
RECORD_KEY_C = "c" * 40


class FakeMilvusCollection:
    """Minimal pymilvus Collection double: query, delete, create_index, num_entities."""

    def __init__(
        self,
        *,
        num_entities: int = 0,
        rows_by_call: list[list[dict]] | None = None,
        query_error: Exception | None = None,
        delete_error: Exception | None = None,
        index_error: Exception | None = None,
        drop_error: Exception | None = None,
    ) -> None:
        """Seed the entity count and the rows returned by successive query() calls."""
        self.num_entities = num_entities
        self._rows_by_call = list(rows_by_call or [])
        self._query_error = query_error
        self._delete_error = delete_error
        self._index_error = index_error
        self._drop_error = drop_error
        self.query_calls: list[dict] = []
        self.delete_calls: list[str] = []
        self.index_calls: list[dict] = []
        self.events: list[str] = []
        self.dropped = False

    def query(self, **kwargs: object) -> list[dict]:
        """Record kwargs and pop the next queued row batch."""
        self.events.append("query")
        self.query_calls.append(kwargs)
        if self._query_error is not None:
            raise self._query_error
        if self._rows_by_call:
            return self._rows_by_call.pop(0)
        return []

    def delete(self, expr: str) -> None:
        """Record the delete expression."""
        self.events.append("delete")
        if self._delete_error is not None:
            raise self._delete_error
        self.delete_calls.append(expr)

    def drop(self) -> None:
        """Record the drop of the whole table, or raise as a failing server would."""
        self.events.append("drop")
        if self._drop_error is not None:
            raise self._drop_error
        self.dropped = True

    def create_index(
        self, field_name: str, index_params: dict, **kwargs: object
    ) -> None:
        """Record the index request, or raise as a server that refuses it would."""
        self.events.append("create_index")
        self.index_calls.append(
            {"field_name": field_name, "index_params": index_params, **kwargs}
        )
        if self._index_error is not None:
            raise self._index_error


class FakeVectorStore:
    """Minimal vector store double exposing LangChain Milvus field names."""

    _primary_field = "pk"
    _text_field = "text"
    _metadata_field = "metadata"

    def __init__(
        self, col: FakeMilvusCollection | None, *, add_error: Exception | None = None
    ) -> None:
        """Wrap a FakeMilvusCollection (or None, for the empty-store case)."""
        self.col = col
        self._add_error = add_error
        self.added: list[list[Document]] = []

    def add_documents(self, documents: list[Document]) -> list[int]:
        """Record the inserted documents, or raise as a failing embedding would."""
        if self.col is not None:
            self.col.events.append("insert")
        if self._add_error is not None:
            raise self._add_error
        self.added.append(documents)
        return list(range(len(documents)))


async def _make_collection(monkeypatch, store: FakeVectorStore) -> Collection:
    collection = Collection(collection_id="collection-id", user_id="internal-service")

    async def fake_details(required_permission="read"):
        return {"table_id": "milvus-table"}

    monkeypatch.setattr(collection, "_get_details_or_raise", fake_details)
    monkeypatch.setattr(collection, "_get_store", lambda table_id: store)
    return collection


@pytest.mark.asyncio
async def test_entity_count_returns_raw_num_entities(monkeypatch) -> None:
    store = FakeVectorStore(FakeMilvusCollection(num_entities=7))
    collection = await _make_collection(monkeypatch, store)

    assert await collection.entity_count() == 7


@pytest.mark.asyncio
async def test_entity_count_is_zero_when_collection_has_no_store(monkeypatch) -> None:
    store = FakeVectorStore(None)
    collection = await _make_collection(monkeypatch, store)

    assert await collection.entity_count() == 0


@pytest.mark.asyncio
async def test_list_raw_entities_passes_limit_and_offset(monkeypatch) -> None:
    rows = [{"pk": 1, "text": "hello", "metadata": {"stream": "users"}}]
    store = FakeVectorStore(FakeMilvusCollection(rows_by_call=[rows]))
    collection = await _make_collection(monkeypatch, store)

    entities = await collection.list_raw_entities(limit=5, offset=10)

    assert entities == [{"content": "hello", "metadata": {"stream": "users"}}]
    assert store.col.query_calls[0]["limit"] == 5
    assert store.col.query_calls[0]["offset"] == 10


@pytest.mark.asyncio
async def test_entity_stats_computes_averages_over_sample(monkeypatch) -> None:
    rows = [{"text": "abcd"}, {"text": "ab"}]
    store = FakeVectorStore(FakeMilvusCollection(rows_by_call=[rows]))
    collection = await _make_collection(monkeypatch, store)

    stats = await collection.entity_stats()

    assert stats["chunk_count"] == 2
    assert stats["avg_chunk_chars"] == 3  # (4 + 2) // 2


@pytest.mark.asyncio
async def test_entity_stats_empty_when_no_rows(monkeypatch) -> None:
    store = FakeVectorStore(FakeMilvusCollection(rows_by_call=[[]]))
    collection = await _make_collection(monkeypatch, store)

    stats = await collection.entity_stats()

    assert stats == {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}


@pytest.mark.asyncio
async def test_clear_deletes_all_rows_and_returns_prior_count(monkeypatch) -> None:
    fake_col = FakeMilvusCollection(num_entities=3)
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    removed = await collection.clear()

    assert removed == 3
    assert fake_col.delete_calls == ["pk >= 0"]


@pytest.mark.asyncio
async def test_clear_is_a_noop_when_collection_has_no_store(monkeypatch) -> None:
    store = FakeVectorStore(None)
    collection = await _make_collection(monkeypatch, store)

    assert await collection.clear() == 0


@pytest.mark.asyncio
async def test_drop_removes_the_table_and_reports_what_it_held(monkeypatch) -> None:
    # The datasource is deleted: its table goes, and the store cache forgets it. A
    # LangChain Milvus store keeps the field list of the table it was built on and
    # appends to it when it initialises again, so a cached store that outlived its
    # table would fail the next write with a schema mismatch instead of creating
    # the table anew (seen against Milvus v2.5.11).
    fake_col = FakeMilvusCollection(num_entities=3)
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)
    documents_service._RECORD_KEY_INDEXED_STORES.add(store)
    cache_key = vectorstore.to_milvus_collection_name("milvus-table")
    monkeypatch.setattr(vectorstore, "_MILVUS_STORES", OrderedDict({cache_key: store}))

    removed = await collection.drop()

    assert removed == 3 and fake_col.dropped
    assert store.col is None
    assert store not in documents_service._RECORD_KEY_INDEXED_STORES
    assert cache_key not in vectorstore._MILVUS_STORES


@pytest.mark.asyncio
async def test_drop_is_a_noop_when_collection_has_no_store(monkeypatch) -> None:
    collection = await _make_collection(monkeypatch, FakeVectorStore(None))

    assert await collection.drop() == 0


@pytest.mark.asyncio
async def test_drop_reports_a_failed_milvus_call(monkeypatch) -> None:
    fake_col = FakeMilvusCollection(num_entities=3, drop_error=MilvusException(message="busy"))
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    with pytest.raises(DatabaseOperationError):
        await collection.drop()
    assert store.col is fake_col


def _chunk(text: str, record_key: str) -> Document:
    return Document(page_content=text, metadata={"_record_key": record_key})


async def test_retire_other_runs_removes_what_the_finishing_run_did_not_write(
    monkeypatch,
) -> None:
    # An overwrite sync lands next to the previous version and retires it at the end:
    # chunks of other runs, and chunks written before runs were tagged at all.
    monkeypatch.setattr(documents_service, "MILVUS_TERM_BATCH_SIZE", 2)
    fake_col = FakeMilvusCollection(rows_by_call=[[{"pk": 1}, {"pk": 2}, {"pk": 3}]])
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    removed = await collection.retire_other_runs("job-7")

    assert removed == 3
    lookup = fake_col.query_calls[0]
    assert lookup["expr"] == (
        '(not exists metadata["_sync_job_id"]) or metadata["_sync_job_id"] != "job-7"'
    )
    assert lookup["output_fields"] == ["pk"] and lookup["consistency_level"] == "Strong"
    assert fake_col.delete_calls == ["pk in [1, 2]", "pk in [3]"]


async def test_retire_other_runs_is_a_noop_for_a_collection_without_a_store(
    monkeypatch,
) -> None:
    collection = await _make_collection(monkeypatch, FakeVectorStore(None))
    assert await collection.retire_other_runs("job-7") == 0


async def test_retire_other_runs_reports_a_failed_delete(monkeypatch) -> None:
    fake_col = FakeMilvusCollection(
        rows_by_call=[[{"pk": 1}]], delete_error=RuntimeError("milvus gone")
    )
    collection = await _make_collection(monkeypatch, FakeVectorStore(fake_col))

    with pytest.raises(DependencyUnavailableError) as raised:
        await collection.retire_other_runs("job-7")
    assert raised.value.details["stage"] == "delete"


async def test_replace_records_inserts_before_it_deletes_the_old_chunks(
    monkeypatch,
) -> None:
    fake_col = FakeMilvusCollection(rows_by_call=[[{"pk": 11}, {"pk": 12}]])
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    replaced = await collection.replace_records(
        [RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)]
    )

    assert replaced == 2
    assert fake_col.events == ["query", "insert", "create_index", "delete"]
    lookup = fake_col.query_calls[0]
    assert lookup["expr"] == f'metadata["_record_key"] in ["{RECORD_KEY_A}"]'
    assert lookup["output_fields"] == ["pk"]
    # The lookup has to see the rows a write stored a moment ago.
    assert lookup["consistency_level"] == "Strong"
    assert [d.page_content for d in store.added[0]] == ["new"]
    assert fake_col.delete_calls == ["pk in [11, 12]"]


async def test_replace_records_deletes_nothing_when_the_insert_fails(
    monkeypatch,
) -> None:
    fake_col = FakeMilvusCollection(rows_by_call=[[{"pk": 11}]])
    store = FakeVectorStore(fake_col, add_error=RuntimeError("embedding model down"))
    collection = await _make_collection(monkeypatch, store)

    with pytest.raises(RuntimeError, match="embedding model down"):
        await collection.replace_records([RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)])

    assert fake_col.events == ["query", "insert"]
    assert fake_col.delete_calls == []


async def test_replace_records_slices_the_lookup_and_the_delete(monkeypatch) -> None:
    monkeypatch.setattr(documents_service, "MILVUS_TERM_BATCH_SIZE", 2)
    fake_col = FakeMilvusCollection(
        rows_by_call=[[{"pk": 1}, {"pk": 2}, {"pk": 3}], [{"pk": 4}, {"pk": 5}]]
    )
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    replaced = await collection.replace_records(
        [RECORD_KEY_A, RECORD_KEY_B, RECORD_KEY_C],
        [_chunk(key, key) for key in (RECORD_KEY_A, RECORD_KEY_B, RECORD_KEY_C)],
    )

    assert replaced == 5
    assert [call["expr"] for call in fake_col.query_calls] == [
        f'metadata["_record_key"] in ["{RECORD_KEY_A}", "{RECORD_KEY_B}"]',
        f'metadata["_record_key"] in ["{RECORD_KEY_C}"]',
    ]
    assert len(store.added) == 1
    assert fake_col.delete_calls == ["pk in [1, 2]", "pk in [3, 4]", "pk in [5]"]


async def test_replace_records_only_inserts_when_nothing_is_stored_yet(
    monkeypatch,
) -> None:
    fake_col = FakeMilvusCollection(rows_by_call=[[]])
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    replaced = await collection.replace_records(
        [RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)]
    )

    assert replaced == 0
    assert fake_col.events == ["query", "insert", "create_index"]


async def test_replace_records_only_inserts_into_a_collection_without_a_store(
    monkeypatch,
) -> None:
    store = FakeVectorStore(None)
    collection = await _make_collection(monkeypatch, store)

    replaced = await collection.replace_records(
        [RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)]
    )

    assert replaced == 0
    assert len(store.added) == 1


async def test_replace_records_inserts_nothing_when_the_lookup_fails(
    monkeypatch,
) -> None:
    fake_col = FakeMilvusCollection(query_error=RuntimeError("milvus down"))
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    with pytest.raises(DependencyUnavailableError) as raised:
        await collection.replace_records([RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)])

    assert raised.value.code == "datasource.replace_failed"
    assert store.added == []


async def test_replace_records_reports_a_delete_that_failed(monkeypatch) -> None:
    fake_col = FakeMilvusCollection(
        rows_by_call=[[{"pk": 11}]], delete_error=RuntimeError("milvus down")
    )
    store = FakeVectorStore(fake_col)
    collection = await _make_collection(monkeypatch, store)

    # The new chunks are stored and the old ones are not removed: the caller
    # has to learn that, so that it sends the batch again.
    with pytest.raises(DependencyUnavailableError) as raised:
        await collection.replace_records([RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)])

    assert raised.value.code == "datasource.replace_failed"
    assert len(store.added) == 1


def _service_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return what the documents service logged at WARNING or above."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == documents_service.logger.name
        and record.levelno >= logging.WARNING
    ]


async def test_replace_records_asks_for_the_record_key_index(monkeypatch) -> None:
    fake_col = FakeMilvusCollection()
    collection = await _make_collection(monkeypatch, FakeVectorStore(fake_col))

    await collection.replace_records([RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)])

    assert fake_col.index_calls == [
        {
            "field_name": "metadata",
            "index_params": {
                "index_type": "INVERTED",
                "params": {
                    # The path the lookup filters on.
                    "json_path": 'metadata["_record_key"]',
                    "json_cast_type": "varchar",
                },
            },
            "index_name": "record_key",
            # Milvus builds the index in the background: the write does not wait.
            "sync": False,
        }
    ]


async def test_replace_records_asks_for_the_index_once_per_store(monkeypatch) -> None:
    fake_col = FakeMilvusCollection()
    collection = await _make_collection(monkeypatch, FakeVectorStore(fake_col))
    other_col = FakeMilvusCollection()
    other = await _make_collection(monkeypatch, FakeVectorStore(other_col))

    await collection.replace_records([RECORD_KEY_A], [_chunk("one", RECORD_KEY_A)])
    await collection.replace_records([RECORD_KEY_A], [_chunk("two", RECORD_KEY_A)])
    await other.replace_records([RECORD_KEY_A], [_chunk("one", RECORD_KEY_A)])

    assert len(fake_col.index_calls) == 1
    assert len(other_col.index_calls) == 1


async def test_replace_records_goes_on_when_the_index_is_refused(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)
    fake_col = FakeMilvusCollection(
        rows_by_call=[[{"pk": 11}]],
        index_error=RuntimeError("json path index is not supported"),
    )
    collection = await _make_collection(monkeypatch, FakeVectorStore(fake_col))

    replaced = await collection.replace_records(
        [RECORD_KEY_A], [_chunk("new", RECORD_KEY_A)]
    )

    # Without the index the lookup is slower, not wrong: the write is complete.
    assert replaced == 1
    assert fake_col.delete_calls == ["pk in [11]"]
    warnings = _service_warnings(caplog)
    assert len(warnings) == 1
    assert "json path index is not supported" in warnings[0]

    # A refusal is not remembered: the next write asks again.
    await collection.replace_records([RECORD_KEY_A], [_chunk("newer", RECORD_KEY_A)])
    assert len(fake_col.index_calls) == 2


async def test_replace_records_asks_for_no_index_while_the_collection_is_missing(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)
    collection = await _make_collection(monkeypatch, FakeVectorStore(None))

    # Nothing to store, so nothing creates the Milvus collection either.
    assert await collection.replace_records([RECORD_KEY_A], []) == 0

    assert _service_warnings(caplog) == []
