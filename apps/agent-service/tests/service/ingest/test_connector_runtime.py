"""The connector runtime end to end: registry, destination, runner, status reporting."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import importlib
from typing import Any

from connector import (
    BaseSource,
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorDefinition,
    ConnectorDisabledError,
    ConnectorKind,
    DestinationSyncMode,
    JobStatus,
    Record,
    RetryPolicy,
    Stream,
    secret_field,
)
from error_contract import ApplicationError
from fastapi import FastAPI, Response
import httpx
from idempotency import (
    AsyncRedisPool,
    IdempotencyConfig,
    IdempotencyMiddleware,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)
from pydantic import BaseModel
import pytest

from service.ingest import connector_runtime
from service.ingest.connector_runtime import (
    CONFIG_MISSING_MESSAGE,
    ConnectorConfigMissingError,
    ConnectorRuntime,
    build_registry,
)
from service.ingest.connector_stores import RAG_DESTINATION
from service.ingest.rag_destination import records_to_documents

DS = "22222222-2222-2222-2222-222222222222"


class _RowsConfig(BaseModel):
    rows: int = 3


class _TwoStreamSource(BaseSource[_RowsConfig]):
    definition = ConnectorDefinition(name="two_streams", display_name="Two", kind=ConnectorKind.SOURCE)
    Config = _RowsConfig

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(streams=[Stream(name="a"), Stream(name="b")])

    async def read(self, catalog: ConfiguredCatalog, state: Any = None) -> AsyncIterator[Record]:
        for configured in catalog.streams:
            for i in range(self.config.rows):
                yield Record(stream=configured.stream.name, data={"id": i + 1, "title": f"row {i + 1}"})


class _RagCalls:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        #: ``(keep_job_id, idempotency_key)`` of every end-of-sync retire call.
        self.retired: list[tuple[str, str | None]] = []

    async def __call__(self, collection_id, documents, *, clear_existing=False, idempotency_key=None, access_token=None):
        self.calls.append(
            {
                "collection_id": collection_id,
                "documents": documents,
                "clear_existing": clear_existing,
                "idempotency_key": idempotency_key,
                "access_token": access_token,
            }
        )
        chunks = len(documents)
        return {"chunks_indexed": chunks, "chunk_char_total": 10 * chunks, "chunk_token_total": 2 * chunks}

    async def retire(self, collection_id, *, keep_job_id, idempotency_key=None, access_token=None):
        self.retired.append((keep_job_id, idempotency_key))
        return {"chunks_removed": 0}


@pytest.fixture
def rag(monkeypatch) -> _RagCalls:
    calls = _RagCalls()
    monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", calls)
    monkeypatch.setattr("service.ingest.rag_destination.retire_datasource_runs", calls.retire)
    return calls


class _KeyConfig(BaseModel):
    api_key: str = secret_field()


class _RejectedSource(BaseSource[_KeyConfig]):
    """Fails the way an HTTP source does: the error quotes the address, key included."""

    definition = ConnectorDefinition(name="rejected", display_name="Rejected", kind=ConnectorKind.SOURCE)

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(streams=[Stream(name="items")])

    async def read(self, catalog: ConfiguredCatalog, state: Any = None) -> AsyncIterator[Record]:
        request = httpx.Request("GET", "https://api.example.com/items", params={"api_key": self.config.api_key})
        httpx.Response(401, request=request).raise_for_status()
        yield Record(stream="items", data={})  # pragma: no cover - never reached


async def _runtime(
    sync_tables, *, mode=DestinationSyncMode.OVERWRITE, config=None, batch_size=2, source=_TwoStreamSource
):
    configs = {"current": config, "asked": [], "checked": []}

    async def read_config(owner_user_id, config_id):
        configs["asked"].append((owner_user_id, config_id))
        if isinstance(configs["current"], Exception):
            raise configs["current"]
        return configs["current"]

    async def config_exists(owner_user_id, config_id):
        configs["checked"].append((owner_user_id, config_id))
        if isinstance(configs["current"], Exception):
            raise configs["current"]
        return configs["current"] is not None

    registry = build_registry()
    registry.register(source)
    runtime = ConnectorRuntime(registry=registry, read_config=read_config, config_exists=config_exists)
    runtime.configs = configs  # test handle: change or inspect what user-service returns
    runtime.runner.options.batch_size = batch_size
    catalog = ConfiguredCatalog.from_catalog(
        await source.from_config(config or {}).discover(), destination_sync_mode=mode
    )
    name = source.definition.name
    sync_tables.datasources.add(DS, connector_type=name)
    await sync_tables.connections.create(DS, name, "cfg-1", "owner-1", catalog.model_dump(mode="json"))
    return runtime


async def _until(condition, timeout: float = 5.0) -> None:
    """Let the event loop run until ``condition()`` holds."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0)


def test_registry_lists_builtin_sources_and_hides_local_filesystem_ones(monkeypatch):
    monkeypatch.delenv("CONNECTORS_ENABLED", raising=False)
    monkeypatch.delenv("CONNECTORS_DISABLED", raising=False)
    registry = build_registry()
    names = {info.name for info in registry.list(ConnectorKind.SOURCE)}

    assert {"postgres", "mysql", "s3", "confluence"} <= names
    assert names.isdisjoint(connector_runtime.LOCAL_FILESYSTEM_CONNECTORS)
    with pytest.raises(ConnectorDisabledError):
        registry.get_source("file_upload")
    assert registry.get_destination(RAG_DESTINATION).definition.kind is ConnectorKind.DESTINATION


def test_deployment_configuration_overrides_the_defaults(monkeypatch):
    monkeypatch.setenv("CONNECTORS_ENABLED", "file_upload")
    monkeypatch.setenv("CONNECTORS_DISABLED", "postgres, mysql")
    names = {info.name for info in build_registry().list(ConnectorKind.SOURCE)}

    assert "file_upload" in names and "jsonl_file" not in names
    assert names.isdisjoint({"postgres", "mysql"})


def test_a_sync_may_run_for_a_day_unless_the_deployment_says_otherwise(sync_tables, monkeypatch):
    monkeypatch.delenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", raising=False)
    assert ConnectorRuntime(registry=build_registry()).runner.options.timeout_seconds == 86400.0

    monkeypatch.setenv("CONNECTOR_SYNC_TIMEOUT_SECONDS", "0")  # no limit
    assert ConnectorRuntime(registry=build_registry()).runner.options.timeout_seconds is None


def test_batch_retries_outlast_a_rag_service_restart():
    """A failed batch is retried under its idempotency key. The package default
    (3 attempts, 1 s / 2 s) gives up in ~3 s, inside a 10 s rag-service restart and
    well inside the 30 s its circuit breaker stays open; the runtime waits longer."""
    policy = ConnectorRuntime(registry=build_registry()).runner.options.retry
    waited = sum(policy.delay(attempt) for attempt in range(1, policy.attempts))
    assert policy.attempts >= 5 and waited >= 60


@pytest.mark.asyncio
async def test_overwrite_sync_streams_every_batch_and_retires_the_previous_version_at_the_end(sync_tables, rag):
    runtime = await _runtime(sync_tables, config={"rows": 3})

    job = await runtime.start_sync(DS)
    done = await runtime.runner.wait(job.id)

    assert done.status is JobStatus.SUCCEEDED and done.records_read == 6
    assert not any(call["clear_existing"] for call in rag.calls), "nothing is cleared up front"
    writes = [call for call in rag.calls if call["documents"]]
    assert sum(len(call["documents"]) for call in writes) == 6
    assert all(call["access_token"] is None for call in rag.calls)
    keys = [call["idempotency_key"] for call in rag.calls]
    assert all(keys) and len(set(keys)) == len(keys)
    # Every write of the run is keyed by the sync job, which is what a retry repeats.
    assert all(key.startswith(f"connector-sync.{DS}.{job.id}.") for key in keys)
    # 3 rows per stream in batches of 2: no empty closing batch reaches rag-service.
    assert [len(call["documents"]) for call in writes] == [2, 2, 1, 1]
    assert writes[0]["documents"][0]["metadata"]["source"] == "connector:two_streams"
    assert writes[0]["documents"][0]["metadata"]["_sync_job_id"] == job.id
    # The previous version stayed searchable until the run was complete, then left.
    assert rag.retired == [(job.id, f"connector-sync.{DS}.{job.id}.retire")]

    meta = sync_tables.datasources.collections[DS]["cmetadata"]
    assert meta["sync_status"] == "completed" and meta["sync_progress"] == 100
    assert meta["chunk_stats"]["chunk_count"] == 6
    assert sync_tables.jobs.rows[job.id]["status"] == "succeeded"
    assert await runtime.latest_job(DS) is not None and not await runtime.is_active(DS)


@pytest.mark.asyncio
async def test_append_sync_does_not_clear_and_a_second_run_gets_new_keys(sync_tables, rag):
    runtime = await _runtime(sync_tables, mode=DestinationSyncMode.APPEND, config={"rows": 1})

    first = await runtime.runner.wait((await runtime.start_sync(DS)).id)
    first_keys = {call["idempotency_key"] for call in rag.calls}
    second = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert first.status is second.status is JobStatus.SUCCEEDED
    assert not any(call["clear_existing"] for call in rag.calls) and rag.retired == []
    assert first_keys.isdisjoint({call["idempotency_key"] for call in rag.calls[len(first_keys) :]})
    assert sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]["chunk_count"] == 4


@pytest.mark.asyncio
async def test_the_graph_build_that_follows_a_sync_does_not_hold_the_sync_slot(sync_tables, rag, monkeypatch):
    # Polling rag-service's graph build (up to 10 minutes) ran inside the job's final status
    # hook, while the job still held the only sync slot: every other datasource waited.
    building = asyncio.Event()
    release = asyncio.Event()
    asked: list[tuple[str, str | None]] = []
    outcome: list[str] = []

    async def slow_rebuild(datasource_id, run_id=None):
        asked.append((datasource_id, run_id))
        building.set()
        try:
            await release.wait()
            outcome.append("completed")
        except asyncio.CancelledError:
            outcome.append("cancelled")
            raise

    monkeypatch.setattr(connector_runtime, "trigger_graph_rag_rebuild", slow_rebuild)
    runtime = await _runtime(sync_tables, config={"rows": 1})
    await sync_tables.connections.update(DS, update_graph_rag=True)

    job = await runtime.start_sync(DS)
    done = await asyncio.wait_for(runtime.runner.wait(job.id), timeout=5)
    await asyncio.wait_for(building.wait(), timeout=5)

    assert done.status is JobStatus.SUCCEEDED and asked == [(DS, job.id)]
    assert not outcome, "the build is still being followed, the sync is over and its slot free"
    assert not await runtime.is_active(DS)
    assert len(runtime.reporter.graph_builds) == 1

    # Stopping the runtime stops following the build; rag-service goes on with it.
    await runtime.stop()
    assert outcome == ["cancelled"] and runtime.reporter.graph_builds == set()


@pytest.mark.asyncio
async def test_a_failed_sync_is_reported_on_the_datasource(sync_tables, monkeypatch):
    async def rag_down(*args, **kwargs):
        raise RuntimeError("rag-service unreachable")

    monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", rag_down)
    runtime = await _runtime(sync_tables, config={"rows": 1})

    done = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert done.status is JobStatus.FAILED
    meta = sync_tables.datasources.collections[DS]["cmetadata"]
    assert meta["sync_status"] == "error" and "rag-service unreachable" in meta["last_error"]


@pytest.mark.asyncio
async def test_a_batch_rag_service_will_not_run_again_fails_the_sync_with_its_first_error(sync_tables, monkeypatch):
    attempts: list[str] = []

    async def rag_failing_once(collection_id, documents, *, clear_existing=False, idempotency_key=None, **_):
        attempts.append(idempotency_key)
        # rag-service keeps the key of a write it refused: a 4xx, then 409 for every retry.
        # ``rag_client`` raises an enveloped answer as ``ApplicationError`` with its status and code.
        status, code = (422, "validation.failed") if len(attempts) == 1 else (409, "idempotency_key_reused")
        raise ApplicationError(status_code=status, code=code, message=f"rag-service said {code}", message_key=None)

    monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", rag_failing_once)
    runtime = await _runtime(sync_tables, config={"rows": 1})
    runtime.runner.options.retry = RetryPolicy(attempts=3, base_delay_seconds=0)

    done = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert done.status is JobStatus.FAILED
    assert len(attempts) == 2 and attempts[0] == attempts[1], "no third attempt: the answer cannot change"
    assert "422" in done.error and "409" not in done.error
    assert "422" in sync_tables.datasources.collections[DS]["cmetadata"]["last_error"]


class _OrdersConfig(BaseModel):
    rows: int = 3
    revision: int = 1


class _OrdersSource(BaseSource[_OrdersConfig]):
    """One stream with a primary key; ``revision`` changes every row and no key."""

    definition = ConnectorDefinition(name="orders_source", display_name="Orders", kind=ConnectorKind.SOURCE)
    Config = _OrdersConfig

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(streams=[Stream(name="orders", source_defined_primary_key=[["id"]])])

    async def read(self, catalog: ConfiguredCatalog, state: Any = None) -> AsyncIterator[Record]:
        for i in range(self.config.rows):
            title = f"order {i + 1}, revision {self.config.revision}"
            yield Record(stream="orders", data={"id": i + 1, "title": title})


class _FakeRedis:
    """The Redis calls of the idempotency middleware, in memory."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        key, token = keys_and_args[0], keys_and_args[1]
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


class _RagService:
    """The records route of rag-service behind the idempotency middleware it mounts.

    The route keeps one version per record key, which is what ``Collection.replace_records``
    does there, and answers each write with the next of ``failures`` after storing it: a
    write that rag-service stored and then reported as failed.
    """

    PATH = "/api/v1/datasources/{collection_id}/records"

    def __init__(self, monkeypatch, *, failures: list[int]) -> None:
        self.stored: dict[str, str] = {}
        self.statuses: list[int] = []
        self.keys: list[str] = []
        failures = list(failures)
        redis = _FakeRedis()

        async def connect(config: IdempotencyConfig) -> _FakeRedis:
            return redis

        monkeypatch.setattr(AsyncRedisPool, "connect", connect)
        self.app = FastAPI()

        @self.app.post(self.PATH)
        async def records(collection_id: str, body: dict[str, Any]) -> Response:
            documents = body["documents"]
            replaced = sum(document["record_key"] in self.stored for document in documents)
            self.stored.update({document["record_key"]: document["content"] for document in documents})
            if documents and failures:
                return Response(
                    '{"error": {"code": "datasource.replace_failed"}}',
                    status_code=failures.pop(0),
                    media_type="application/json",
                )
            chunks = len(documents)
            return Response(
                f'{{"chunks_indexed": {chunks}, "chunk_char_total": {10 * chunks},'
                f' "chunk_token_total": {2 * chunks}, "chunks_replaced": {replaced}}}',
                media_type="application/json",
            )

        self.app.add_middleware(
            IdempotencyMiddleware,
            config=IdempotencyConfig(
                redis_host="unused",
                redis_port=0,
                redis_db=0,
                redis_password="",
                service_name="rag-service",
                # What rag-service declares for this route (its test_idempotency_policy.py).
                policy=IdempotencyPolicyConfig(
                    default_mode=IdempotencyMode.OPTIONAL_REPLAY,
                    route_policies=[
                        IdempotencyPolicy(
                            method="POST",
                            path=self.PATH,
                            mode=IdempotencyMode.DOMAIN_REQUIRED,
                            enforce_missing_key=True,
                            rerun_after_failure=True,
                        )
                    ],
                ),
            ),
        )
        monkeypatch.setattr("service.ingest.rag_destination.ingest_datasource_records", self.ingest)

    async def ingest(self, collection_id, documents, *, clear_existing=False, idempotency_key=None, access_token=None):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://rag-service") as client:
            response = await client.post(
                self.PATH.format(collection_id=collection_id),
                headers={"Idempotency-Key": idempotency_key},
                json={"documents": documents, "clear_existing": clear_existing},
            )
        self.keys.append(idempotency_key)
        self.statuses.append(response.status_code)
        response.raise_for_status()
        return response.json()


@pytest.mark.asyncio
async def test_a_write_rag_service_failed_is_retried_and_leaves_one_version_of_each_record(sync_tables, monkeypatch):
    rag_service = _RagService(monkeypatch, failures=[503])
    runtime = await _runtime(
        sync_tables, mode=DestinationSyncMode.APPEND, config={"rows": 3, "revision": 1}, source=_OrdersSource
    )
    runtime.runner.options.retry = RetryPolicy(attempts=3, base_delay_seconds=0)

    first = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert first.status is JobStatus.SUCCEEDED, first.error
    # The write that failed and its retry carry one key, and rag-service ran both.
    assert rag_service.statuses == [503, 200, 200]
    assert rag_service.keys[0] == rag_service.keys[1] != rag_service.keys[2]
    assert sorted(rag_service.stored.values()) == [f"id: {i}\ntitle: order {i}, revision 1" for i in (1, 2, 3)]

    # Every row changes at the source and keeps its primary key: the next sync, which
    # appends, replaces the three records instead of storing a second version of each.
    runtime.configs["current"] = {"rows": 3, "revision": 2}
    second = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert second.status is JobStatus.SUCCEEDED, second.error
    assert sorted(rag_service.stored.values()) == [f"id: {i}\ntitle: order {i}, revision 2" for i in (1, 2, 3)]
    assert sync_tables.datasources.collections[DS]["cmetadata"]["chunk_stats"]["chunk_count"] == 3


@pytest.mark.asyncio
async def test_start_sync_refuses_unknown_datasources_and_missing_configs(sync_tables, rag):
    runtime = await _runtime(sync_tables, config=None)

    with pytest.raises(LookupError):
        await runtime.start_sync("33333333-3333-3333-3333-333333333333")
    with pytest.raises(ConnectorConfigMissingError, match="configuration is missing"):
        await runtime.start_sync(DS)
    assert CONFIG_MISSING_MESSAGE.startswith("the stored connector configuration is missing")
    assert sync_tables.jobs.rows == {}
    assert "sync_status" not in sync_tables.datasources.collections[DS]["cmetadata"], "nothing started"


@pytest.mark.asyncio
async def test_the_config_is_fetched_when_a_sync_runs_not_when_connections_are_read(sync_tables, rag):
    runtime = await _runtime(sync_tables, config={"rows": 1})

    assert (await runtime.connections.get(DS)).source_config == {}
    await runtime.connections.list()
    assert runtime.configs["asked"] == [], "looking a connection up must not pull its credentials"

    done = await runtime.runner.wait((await runtime.start_sync(DS)).id)
    assert done.status is JobStatus.SUCCEEDED
    # The trigger only asks whether the configuration still exists (metadata, no
    # credentials); the job that runs is the one read of the configuration.
    assert runtime.configs["checked"] == [("owner-1", "cfg-1")]
    assert runtime.configs["asked"] == [("owner-1", "cfg-1")]


@pytest.mark.asyncio
async def test_a_refused_trigger_reads_no_configuration_and_leaves_the_status_alone(sync_tables, rag):
    runtime = await _runtime(sync_tables, config={"rows": 50}, batch_size=1)
    meta = sync_tables.datasources.collections[DS]

    job = await runtime.start_sync(DS)
    assert meta["cmetadata"]["sync_status"] == "starting" and meta["cmetadata"]["sync_progress"] == 0
    await _until(lambda: meta["cmetadata"]["sync_status"] == "syncing" and len(runtime.configs["asked"]) == 1)
    # user-service going away must not matter to a trigger that starts nothing.
    runtime.configs["current"] = RuntimeError("user-service unreachable")

    assert await runtime.start_sync(DS) is None

    assert len(runtime.configs["asked"]) == 1, "a refused trigger must not pull the credentials"
    assert len(runtime.configs["checked"]) == 1, "nor ask user-service anything"
    assert meta["cmetadata"]["sync_status"] == "syncing", "the running sync keeps its status"
    assert (await runtime.runner.wait(job.id)).status is JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_a_source_error_reaches_the_datasource_without_its_credentials(sync_tables, rag):
    runtime = await _runtime(sync_tables, source=_RejectedSource, config={"api_key": "key-SECRET-123"})

    done = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert done.status is JobStatus.FAILED
    shown = sync_tables.datasources.collections[DS]["cmetadata"]["last_error"]
    stored = sync_tables.jobs.rows[done.id]["error"]
    assert "401" in shown and "https://api.example.com/items?***" in shown
    assert "key-SECRET-123" not in shown + stored


def test_the_spark_connect_client_imports_in_this_environment():
    # The spark connector's default transport. pyspark-client compares the protobuf
    # runtime with its generated code when it is imported and declares no dependency
    # on protobuf, so nothing but this service's own pin keeps the two compatible.
    importlib.import_module("pyspark.sql.connect.session")


@pytest.mark.asyncio
async def test_a_scheduled_run_whose_config_is_gone_fails_as_a_job_with_the_reason(sync_tables, rag):
    runtime = await _runtime(sync_tables, config=None)
    connection = await runtime.connections.get(DS)

    # The scheduler starts runs through the runner, without the start_sync pre-check.
    done = await runtime.runner.wait((await runtime.runner.start(connection)).id)

    assert done.status is JobStatus.FAILED and CONFIG_MISSING_MESSAGE in done.error
    meta = sync_tables.datasources.collections[DS]["cmetadata"]
    assert meta["sync_status"] == "error" and CONFIG_MISSING_MESSAGE in meta["last_error"]
    assert rag.calls == []


@pytest.mark.asyncio
async def test_a_job_left_by_a_dead_replica_does_not_block_the_datasource(sync_tables, rag):
    from datetime import UTC, datetime, timedelta

    runtime = await _runtime(sync_tables, config={"rows": 1})
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    await sync_tables.jobs.create(
        "dead-job", DS, status="running", trigger="manual", stats={}, error=None, worker_id="gone",
        heartbeat_at=long_ago, created_at=long_ago, started_at=long_ago, finished_at=None,
    )

    done = await runtime.runner.wait((await runtime.start_sync(DS)).id)

    assert done.status is JobStatus.SUCCEEDED
    assert sync_tables.jobs.rows["dead-job"]["status"] == "failed"
    assert "stopped responding" in sync_tables.jobs.rows["dead-job"]["error"]


@pytest.mark.asyncio
async def test_a_job_closed_for_a_dead_worker_is_reported_on_the_datasource(sync_tables, rag):
    from datetime import UTC, datetime, timedelta

    runtime = await _runtime(sync_tables, config={"rows": 1})
    meta = sync_tables.datasources.collections[DS]
    meta["cmetadata"]["sync_status"] = "syncing"  # what the worker that died last reported
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    await sync_tables.jobs.create(
        "dead-job", DS, status="running", trigger="manual", stats={}, error=None, worker_id="gone",
        heartbeat_at=long_ago, created_at=long_ago, started_at=long_ago, finished_at=None,
    )

    recovered = await runtime.runner.recover_interrupted(connector_runtime.STALE_AFTER_SECONDS)

    # Nobody else will ever report the end of that job: without this the datasource
    # would show "syncing" until someone started it again.
    assert [job.id for job in recovered] == ["dead-job"]
    assert meta["cmetadata"]["sync_status"] == "error"
    assert "interrupted" in meta["cmetadata"]["last_error"]


@pytest.mark.asyncio
async def test_a_second_start_while_syncing_returns_none(sync_tables, rag):
    runtime = await _runtime(sync_tables, config={"rows": 50}, batch_size=1)

    job = await runtime.start_sync(DS)
    assert await runtime.start_sync(DS) is None
    assert (await runtime.runner.wait(job.id)).status is JobStatus.SUCCEEDED


def test_records_become_text_documents_with_metadata():
    documents = records_to_documents(
        [
            {"id": 7, "title": "Invoice", "body": "Total due", "_internal": "x", "empty": None},
            {"amount": 12, "currency": "TRY"},
            {},
            "not-a-record",
        ],
        "invoices",
        "postgres",
    )

    assert [doc["content"] for doc in documents] == [
        "id: 7\ntitle: Invoice\nTotal due",
        "amount: 12\ncurrency: TRY",
    ]
    # The body is the content; it is not repeated in the metadata of every chunk.
    assert documents[0]["metadata"] == {
        "source": "connector:postgres",
        "stream": "invoices",
        "connector_type": "postgres",
        "id": 7,
        "title": "Invoice",
    }
