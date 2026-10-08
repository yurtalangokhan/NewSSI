"""``RagDatasourceDestination`` against the contract of rag-service's records route."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from connector import (
    Batch,
    Catalog,
    ConfiguredCatalog,
    ConfiguredStream,
    DestinationSyncMode,
    DestinationWriteError,
    Record,
    Stream,
)
from error_contract import ApplicationError, DependencyTimeoutError, from_httpx_error
import httpx
from idempotency import IdempotencyMiddleware
import pytest

from core.http import outbound, rag_http
from service.ingest import ingestion_service
from service.ingest.rag_destination import (
    RagDatasourceConfig,
    RagDatasourceDestination,
    record_key,
    records_to_documents,
)

DS = "22222222-2222-2222-2222-222222222222"
JOB = "5d8b3f3e-0b3f-4b1e-9c56-6c7a2f1f0001"
#: Names a source may give a stream: plain, with spaces / a slash / non-ASCII, very long.
STREAMS = ("orders", "Müşteri siparişleri / 2024", "s" * 300)


def _accepted(key: str) -> bool:
    """rag-service's own rule for an ``Idempotency-Key``: the middleware it mounts."""
    return IdempotencyMiddleware._is_valid_key(key)


class _RagCalls:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.clears = 0
        self.documents: list[dict[str, Any]] = []
        #: ``(keep_job_id, idempotency_key)`` of every end-of-sync retire call.
        self.retired: list[tuple[str, str | None]] = []
        self.chunks_removed = 0

    async def __call__(self, collection_id, documents, *, clear_existing=False, idempotency_key=None, access_token=None):
        self.keys.append(idempotency_key)
        self.clears += int(clear_existing)
        self.documents.extend(documents)
        return {"chunks_indexed": len(documents), "chunk_char_total": 0, "chunk_token_total": 0}

    async def retire(self, collection_id, *, keep_job_id, idempotency_key=None, access_token=None):
        self.keys.append(idempotency_key)
        self.retired.append((keep_job_id, idempotency_key))
        return {"chunks_removed": self.chunks_removed}


@pytest.fixture
def rag(monkeypatch) -> _RagCalls:
    calls = _RagCalls()
    monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", calls)
    monkeypatch.setattr("service.ingest.rag_destination.retire_datasource_runs", calls.retire)
    return calls


def _batch(stream: str, index: int = 0) -> Batch:
    return Batch(
        stream=stream,
        records=[Record(stream=stream, data={"id": 1, "title": "row"})],
        batch_index=index,
        connection_id=DS,
        job_id=JOB,
    )


def _catalog(mode: DestinationSyncMode = DestinationSyncMode.OVERWRITE) -> ConfiguredCatalog:
    return ConfiguredCatalog.from_catalog(
        Catalog(streams=[Stream(name=name) for name in STREAMS]), destination_sync_mode=mode
    )


async def _begun_destination(sync_tables) -> tuple[RagDatasourceDestination, ConfiguredCatalog]:
    sync_tables.datasources.add(DS)
    destination = RagDatasourceDestination(RagDatasourceConfig(datasource_id=DS, connector_type="postgres"))
    catalog = _catalog()
    await destination.begin(catalog, DS, job_id=JOB)
    return destination, catalog


@pytest.mark.asyncio
async def test_every_key_of_a_sync_is_one_rag_service_accepts(sync_tables, rag):
    destination, catalog = await _begun_destination(sync_tables)

    for stream in STREAMS:
        for index in (0, 1):
            await destination.write(_batch(stream, index))
    await destination.finalize(catalog, DS, job_id=JOB)

    assert len(rag.keys) == 2 * len(STREAMS) + 1, "one write per batch, then the retire"
    rejected = [key for key in rag.keys if not _accepted(key)]
    assert not rejected, f"rag-service answers 400 idempotency_key_invalid to {rejected}"
    assert len(set(rag.keys)) == len(rag.keys), "each write of the run has its own key"
    assert all(key.startswith(f"connector-sync.{DS}.{JOB}.") for key in rag.keys)


@pytest.mark.asyncio
async def test_an_overwrite_sync_replaces_the_previous_version_only_once_it_is_complete(sync_tables, rag):
    # The collection used to be cleared in ``begin``: a failed run, or just a slow one,
    # left the datasource empty. The run now lands next to the previous version, every
    # document tagged with its job, and retires everything else at the end.
    rag.chunks_removed = 10
    destination, catalog = await _begun_destination(sync_tables)
    assert rag.clears == 0 and rag.retired == []
    sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"] = {  # the previous version
        "chunk_count": 10,
        "avg_chunk_chars": 100,
        "avg_chunk_tokens": 20,
        "_total_chunk_chars": 1000,
        "_total_chunk_tokens": 200,
    }

    await destination.write(_batch("orders", 0))
    assert all(document["metadata"]["_sync_job_id"] == JOB for document in rag.documents)
    assert rag.retired == [], "the previous version is still searchable while the run writes"

    await destination.finalize(catalog, DS, job_id=JOB)
    assert rag.retired == [(JOB, f"connector-sync.{DS}.{JOB}.retire")]
    stats = sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]
    assert stats["chunk_count"] == 1, "the previous version's 10 chunks left with the retire"


@pytest.mark.asyncio
async def test_an_append_sync_retires_nothing(sync_tables, rag):
    sync_tables.datasources.add(DS)
    destination = RagDatasourceDestination(RagDatasourceConfig(datasource_id=DS, connector_type="postgres"))
    catalog = _catalog(DestinationSyncMode.APPEND)
    await destination.begin(catalog, DS, job_id=JOB)
    await destination.write(_batch("orders", 0))
    await destination.finalize(catalog, DS, job_id=JOB)
    assert rag.retired == [] and rag.clears == 0


@pytest.mark.asyncio
async def test_a_catalog_mixing_overwrite_and_append_is_not_retired(sync_tables, rag, caplog):
    # Stream names are free text and cannot scope a Milvus filter; a retire would take the
    # append streams' history with it. The mix is logged and left in place.
    sync_tables.datasources.add(DS)
    destination = RagDatasourceDestination(RagDatasourceConfig(datasource_id=DS, connector_type="postgres"))
    catalog = ConfiguredCatalog(
        streams=[
            ConfiguredStream(stream=Stream(name="orders"), destination_sync_mode=DestinationSyncMode.OVERWRITE),
            ConfiguredStream(stream=Stream(name="events"), destination_sync_mode=DestinationSyncMode.APPEND),
        ]
    )
    await destination.begin(catalog, DS, job_id=JOB)
    with caplog.at_level("WARNING"):
        await destination.finalize(catalog, DS, job_id=JOB)
    assert rag.retired == [] and "mixes overwrite and append" in caplog.text


@pytest.mark.asyncio
async def test_a_retried_batch_repeats_its_key(sync_tables, rag):
    destination, _ = await _begun_destination(sync_tables)

    await destination.write(_batch(STREAMS[1], 3))
    await destination.write(_batch(STREAMS[1], 3))

    assert rag.keys[-1] == rag.keys[-2]


def _rag_answer(status: int, code: str, message: str) -> dict[str, Any]:
    """An error answer of rag-service, in the envelope its middleware and routes send."""
    return {
        "status": status,
        "body": {"statusCode": status, "message": message, "data": None, "error": {"code": code, "message": message}},
    }


def _answers(monkeypatch, *outcomes: Any) -> list[str]:
    """Make rag-service answer each write with the next outcome; returns the keys it saw.

    The real ``rag_client`` runs: what reaches the destination is what it raises for an
    enveloped error (``ApplicationError``) or a transport failure (``from_httpx_error``),
    never an ``httpx`` exception.
    """
    keys: list[str] = []
    pending = list(outcomes)

    async def fake_outbound(dependency, method, url, *, headers=None, json=None, **kwargs):
        keys.append((headers or {}).get("Idempotency-Key"))
        outcome = pending.pop(0)
        if isinstance(outcome, httpx.HTTPError):
            raise from_httpx_error(outcome) from outcome  # what ``outbound.request`` does
        request = httpx.Request(method, url)
        if "status" in outcome:
            return httpx.Response(outcome["status"], json=outcome["body"], request=request)
        envelope = {"statusCode": 200, "message": "ok", "data": outcome, "error": None}
        return httpx.Response(200, json=envelope, request=request)

    monkeypatch.setattr(outbound, "request", fake_outbound)
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag-service")
    return keys


@pytest.mark.asyncio
async def test_a_retry_rag_service_refuses_stops_with_the_first_failure_as_the_reason(sync_tables, monkeypatch):
    # rag-service frees the key of a write that failed with 429 / 5xx. A write it refused
    # for another reason keeps its key: the same key gets 409 from then on.
    invalid = _rag_answer(422, "validation.failed", "documents.0.record_key is not a SHA-1")
    reused = _rag_answer(409, "idempotency_key_reused", "Idempotency-Key was already used")
    keys = _answers(monkeypatch, invalid, reused)
    destination, _ = await _begun_destination(sync_tables)

    with pytest.raises(ApplicationError) as first:
        await destination.write(_batch("orders"))
    with pytest.raises(DestinationWriteError, match="422") as refused:
        await destination.write(_batch("orders"))

    assert first.value.status_code == 422 and keys[0] == keys[1]
    assert refused.value.__cause__ is first.value
    assert "will not run" in str(refused.value) and "409" not in str(refused.value)


@pytest.mark.asyncio
async def test_a_write_rag_service_failed_runs_again_under_the_same_key(sync_tables, monkeypatch):
    # After a 5xx rag-service runs the same key again: the retry is an ordinary write.
    unavailable = _rag_answer(503, "datasource.replace_failed", "milvus timeout")
    done = {"chunks_indexed": 1, "chunk_char_total": 4, "chunk_token_total": 1, "chunks_replaced": 1}
    keys = _answers(monkeypatch, unavailable, done)
    destination, _ = await _begun_destination(sync_tables)

    with pytest.raises(ApplicationError) as failed:
        await destination.write(_batch("orders"))
    assert failed.value.status_code == 503 and not isinstance(failed.value, DestinationWriteError)
    assert (await destination.write(_batch("orders"))).records_written == 1

    assert keys[0] == keys[1]


@pytest.mark.asyncio
async def test_a_request_still_in_progress_is_left_to_the_runner_to_retry(sync_tables, monkeypatch):
    # Same status, other code: the first attempt may still finish, and then the retry replays it.
    in_progress = _rag_answer(409, "idempotency_request_in_progress", "still in progress")
    done = {"chunks_indexed": 1, "chunk_char_total": 4, "chunk_token_total": 1}
    _answers(monkeypatch, httpx.ReadTimeout("no answer in time"), in_progress, done)
    destination, _ = await _begun_destination(sync_tables)

    with pytest.raises(DependencyTimeoutError):
        await destination.write(_batch("orders"))
    with pytest.raises(ApplicationError) as waiting:
        await destination.write(_batch("orders"))
    assert waiting.value.status_code == 409 and not isinstance(waiting.value, DestinationWriteError)
    assert (await destination.write(_batch("orders"))).records_written == 1


def test_a_record_key_is_made_of_the_primary_key_of_the_stream():
    documents = records_to_documents(
        [{"id": 7, "title": "first"}, {"id": 7, "title": "edited"}, {"id": 8, "title": "first"}],
        "orders",
        "postgres",
        primary_key=[["id"]],
    )

    keys = [doc["record_key"] for doc in documents]
    assert keys[0] == keys[1] != keys[2], "a changed record keeps its key, another record has another"
    assert all(re.fullmatch(r"[0-9a-f]{40}", key) for key in keys), "the shape rag-service accepts"
    # The same primary key in another stream is another record.
    assert record_key("invoices", {"id": 7, "title": "first"}, [["id"]]) != keys[0]


def test_chunk_metadata_stays_small_and_leaves_the_body_to_the_content():
    # rag-service copies the metadata onto every chunk and Milvus stores it as one JSON
    # field of at most 64 KiB: a record's body in there meant ~50x the storage, the whole
    # record in every hit, and a 5xx (and a failed job) for a record over the limit.
    import json

    body = "word " * 15_000  # 75 KB
    record = {
        "id": 7,
        "title": "Invoice",
        "body": body,
        "description": "d" * 10_000,
        "tags": ["a", "b"],
        "attrs": {"x": "y" * 5_000},
        **{f"col_{i}": "v" * 1_000 for i in range(60)},
    }

    [document] = records_to_documents([record], "orders", "postgres", primary_key=[["id"]])

    assert document["content"].startswith("id: 7\ntitle: Invoice\n") and body.strip() in document["content"]
    metadata = document["metadata"]
    assert "body" not in metadata, "the text is the content, not metadata of every chunk"
    assert metadata["id"] == 7 and metadata["title"] == "Invoice" and metadata["tags"] == ["a", "b"]
    assert len(metadata["description"]) == 4_096, "a long value is cut, not dropped"
    assert "attrs" not in metadata, "a nested value over the limit is dropped"
    assert len(json.dumps(metadata, ensure_ascii=False)) <= 32_768
    assert {"source", "stream", "connector_type"} <= metadata.keys()


def test_a_composite_or_nested_primary_key_names_the_record():
    primary_key = [["tenant"], ["ref", "id"]]
    row = {"tenant": "t1", "ref": {"id": 1}, "note": "x"}

    key = record_key("orders", row, primary_key)

    assert key == record_key("orders", {**row, "note": "changed"}, primary_key)
    assert key != record_key("orders", {**row, "tenant": "t2"}, primary_key)
    assert key != record_key("orders", {**row, "ref": {"id": 2}}, primary_key)


def test_a_record_without_primary_key_values_is_named_by_its_content():
    row = {"amount": 12, "currency": "TRY", "at": datetime(2026, 1, 2, tzinfo=UTC)}

    key = record_key("payments", row)

    assert key == record_key("payments", dict(reversed(row.items()))), "the order of the fields does not matter"
    assert key != record_key("payments", {**row, "amount": 13})
    assert key != record_key("refunds", row)
    # A primary key the record has no value for cannot name it.
    assert record_key("payments", row, [["id"]]) == key
    assert record_key("payments", {**row, "id": None}, [["id"]]) == record_key("payments", {**row, "id": None})
    assert record_key("payments", {**row, "ref": "plain"}, [["ref", "id"]]) == record_key(
        "payments", {**row, "ref": "plain"}
    )


@pytest.mark.asyncio
async def test_documents_carry_the_record_key_of_the_configured_primary_key(sync_tables, monkeypatch):
    sent: dict[str, list[dict[str, Any]]] = {}

    async def ingest(collection_id, documents, *, clear_existing=False, idempotency_key=None, access_token=None):
        for document in documents:
            sent.setdefault(document["metadata"]["stream"], []).append(document)
        return {"chunks_indexed": len(documents), "chunk_char_total": 0, "chunk_token_total": 0}

    monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", ingest)
    sync_tables.datasources.add(DS)
    destination = RagDatasourceDestination(RagDatasourceConfig(datasource_id=DS, connector_type="postgres"))
    append = DestinationSyncMode.APPEND
    catalog = ConfiguredCatalog(
        streams=[
            # The key the sync was configured with wins over the one the source declares.
            ConfiguredStream(
                stream=Stream(name="customers", source_defined_primary_key=[["id"]]),
                destination_sync_mode=append,
                primary_key=[["email"]],
            ),
            ConfiguredStream(
                stream=Stream(name="orders", source_defined_primary_key=[["id"]]), destination_sync_mode=append
            ),
            ConfiguredStream(stream=Stream(name="events"), destination_sync_mode=append),
        ]
    )
    await destination.begin(catalog, DS, job_id=JOB)

    for stream, row in (
        ("customers", {"id": 1, "email": "a@example.com", "name": "Ada"}),
        ("orders", {"id": 1, "title": "row"}),
        ("events", {"id": 1, "title": "row"}),
    ):
        batch = Batch(stream=stream, records=[Record(stream=stream, data=row)], batch_index=0, job_id=JOB)
        await destination.write(batch)

    assert sent["customers"][0]["record_key"] == record_key("customers", {"email": "a@example.com"}, [["email"]])
    assert sent["orders"][0]["record_key"] == record_key("orders", {"id": 1}, [["id"]])
    assert sent["events"][0]["record_key"] == record_key("events", {"id": 1, "title": "row"})


@pytest.mark.asyncio
async def test_replaced_chunks_leave_the_chunk_statistics(sync_tables, monkeypatch):
    _answers(
        monkeypatch,
        {"chunks_indexed": 4, "chunk_char_total": 400, "chunk_token_total": 100, "chunks_replaced": 0},
        {"chunks_indexed": 2, "chunk_char_total": 300, "chunk_token_total": 60, "chunks_replaced": 2},
        # A rag-service that does not report replacements yet: nothing was replaced.
        {"chunks_indexed": 1, "chunk_char_total": 50, "chunk_token_total": 10},
    )
    destination, _ = await _begun_destination(sync_tables)

    await destination.write(_batch("orders", 0))
    await destination.write(_batch("orders", 1))
    stats = sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]

    # 4 chunks of 100 characters; 2 of them leave at that average and 2 of 150 arrive.
    assert stats["chunk_count"] == 4
    assert stats["_total_chunk_chars"] == 500 and stats["avg_chunk_chars"] == 125
    assert stats["_total_chunk_tokens"] == 110 and stats["avg_chunk_tokens"] == 27

    await destination.write(_batch("orders", 2))
    stats = sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]
    assert stats["chunk_count"] == 5 and stats["_total_chunk_chars"] == 550


@pytest.mark.asyncio
async def test_chunk_statistics_never_go_below_zero(sync_tables, monkeypatch):
    # More chunks replaced than the statistics know of: they were reset, or a write that
    # rag-service stored and then failed was never counted.
    _answers(
        monkeypatch,
        {"chunks_indexed": 1, "chunk_char_total": 80, "chunk_token_total": 20, "chunks_replaced": 5},
        {"chunks_indexed": 0, "chunk_char_total": 0, "chunk_token_total": 0, "chunks_replaced": 3},
    )
    destination, _ = await _begun_destination(sync_tables)

    await destination.write(_batch("orders", 0))
    stats = sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]
    assert stats["chunk_count"] == 1 and stats["avg_chunk_chars"] == 80

    # Records whose new version gave no chunk at all still take their old chunks away.
    await destination.write(_batch("orders", 1))
    stats = sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]
    assert stats == {
        "chunk_count": 0,
        "avg_chunk_chars": 0,
        "avg_chunk_tokens": 0,
        "_total_chunk_chars": 0,
        "_total_chunk_tokens": 0,
    }


@pytest.mark.asyncio
async def test_the_graph_rebuild_key_is_one_rag_service_accepts(sync_tables, monkeypatch):
    sync_tables.datasources.add(DS)
    sent: dict[str, Any] = {}

    async def request(dependency, method, url, **kwargs):
        sent.update(method=method, url=url, headers=kwargs["headers"])
        error = httpx.ConnectError("nothing listens here")
        raise from_httpx_error(error) from error  # what ``outbound.request`` does

    monkeypatch.setattr(rag_http, "rag_base_url", lambda: "http://rag-service")
    monkeypatch.setattr(outbound, "request", request)

    await ingestion_service.trigger_graph_rag_rebuild(DS, run_id=JOB)

    assert sent["method"] == "POST" and sent["url"].endswith("/graph/build")
    key = sent["headers"]["Idempotency-Key"]
    assert _accepted(key), f"rag-service answers 400 idempotency_key_invalid to {key!r}"
    assert key == f"graph-build.{DS}.{JOB}"
    # An unreachable rag-service is "unavailable", not a failed build.
    assert sync_tables.datasources.collections[DS]["cmetadata"]["graph_update_status"] == "graph_unavailable"


@pytest.mark.asyncio
async def test_a_graph_build_rag_service_refuses_is_reported_as_failed(sync_tables, monkeypatch):
    sync_tables.datasources.add(DS)
    _answers(monkeypatch, _rag_answer(409, "graph.build_in_progress", "a build is already running"))

    await ingestion_service.trigger_graph_rag_rebuild(DS, run_id=JOB)

    meta = sync_tables.datasources.collections[DS]["cmetadata"]
    assert meta["graph_update_status"] == "graph_failed"
    assert "already running" in meta["graph_update_error"]
