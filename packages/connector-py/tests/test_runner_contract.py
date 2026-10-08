"""What the runner promises its collaborators: factory, hooks, destination lifecycle, job claims."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from connector import (
    BaseDestination,
    Batch,
    CheckFailedError,
    CheckResult,
    ConfiguredCatalog,
    Connection,
    ConnectorDefinition,
    ConnectorFactory,
    ConnectorKind,
    ConnectorRegistry,
    DestinationWriteError,
    ExclusiveJobStore,
    InMemoryJobStore,
    Job,
    JobNotFoundError,
    JobStatus,
    MissingExtraError,
    Record,
    RegistryConnectorFactory,
    RetryPolicy,
    State,
    SyncAlreadyRunningError,
    SyncOptions,
    SyncRunner,
    SyncState,
    WriteResult,
)
from connector.destinations.memory import InMemoryDestination
from connector.extras import require_extra
from connector.models import utcnow
from tests.conftest import FakeSource


async def _connection(source: str = "fake", rows: int = 5) -> Connection:
    src = FakeSource.from_config({"rows": rows})
    return Connection(
        name="c",
        source_name=source,
        source_config={"rows": rows},
        destination_name="memory",
        destination_config={},
        catalog=ConfiguredCatalog.from_catalog(await src.discover()),
    )


class _Config(BaseModel):
    pass


class RecordingDestination(BaseDestination[_Config]):
    """Instance-level sink: only reachable through a factory."""

    definition = ConnectorDefinition(
        name="recording", display_name="Recording", kind=ConnectorKind.DESTINATION
    )
    Config = _Config

    def __init__(self, config: _Config | None = None) -> None:
        super().__init__(config or _Config())
        self.batches: list[Batch] = []
        self.events: list[str] = []
        self.fail_with: Exception | None = None
        self.closed = False

    async def check(self) -> CheckResult:
        return CheckResult(ok=True)

    async def begin(self, catalog: Any, connection_id: str | None = None, *, job_id=None) -> None:
        self.events.append("begin")

    async def write(self, batch: Batch) -> WriteResult:
        if self.fail_with is not None:
            self.events.append("write-failed")
            raise self.fail_with
        self.batches.append(batch)
        return WriteResult(records_written=batch.size)

    async def finalize(self, catalog: Any, connection_id: str | None = None, *, job_id=None):
        self.events.append("finalize")

    async def abort(
        self, catalog: Any, connection_id: str | None = None, *, job_id=None, error=None
    ) -> None:
        self.events.append(f"abort:{type(error).__name__}")

    async def close(self) -> None:
        self.closed = True


class _Factory:
    """A host-provided factory: the source from wherever, a destination instance of its own."""

    def __init__(self, destination: BaseDestination[Any], source: Any = None) -> None:
        self._destination = destination
        self._source = source
        self.calls: list[str] = []

    async def source(self, connection: Connection) -> Any:
        self.calls.append("source")
        return self._source or FakeSource.from_config(connection.source_config)

    async def destination(self, connection: Connection) -> BaseDestination[Any]:
        self.calls.append("destination")
        return self._destination


# ---- factory ----------------------------------------------------------------------


async def test_runner_takes_connectors_from_a_factory() -> None:
    destination = RecordingDestination()
    factory = _Factory(destination)
    assert isinstance(factory, ConnectorFactory)

    job = await SyncRunner(factory, options=SyncOptions(batch_size=2)).run(await _connection())

    assert job.status is JobStatus.SUCCEEDED and job.records_written == 5
    assert factory.calls == ["source", "destination"]
    assert destination.events == ["begin", "finalize"]
    assert destination.closed


async def test_a_registry_is_wrapped_in_the_default_factory(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry)
    assert isinstance(runner.factory, RegistryConnectorFactory)
    assert (await runner.run(await _connection())).status is JobStatus.SUCCEEDED


async def test_a_factory_failure_is_a_failed_job_not_an_exception() -> None:
    class Unavailable:
        async def source(self, connection: Connection) -> Any:
            raise LookupError("the stored configuration is gone")

        async def destination(self, connection: Connection) -> Any:
            raise AssertionError("not reached")

    job = await SyncRunner(Unavailable()).run(await _connection())
    assert job.status is JobStatus.FAILED
    assert job.error == "LookupError: the stored configuration is gone"


# ---- destination lifecycle ----------------------------------------------------------


async def test_a_failed_run_aborts_instead_of_finalizing() -> None:
    destination = RecordingDestination()
    destination.fail_with = ConnectionError("down")
    options = SyncOptions(retry=RetryPolicy(attempts=2, base_delay_seconds=0))

    job = await SyncRunner(_Factory(destination), options=options).run(await _connection())

    assert job.status is JobStatus.FAILED
    assert destination.events == [
        "begin",
        "write-failed",
        "write-failed",
        "abort:DestinationWriteError",
    ]
    assert destination.closed


async def test_destination_write_error_is_not_retried() -> None:
    destination = RecordingDestination()
    destination.fail_with = DestinationWriteError("rejected for good")
    options = SyncOptions(retry=RetryPolicy(attempts=5, base_delay_seconds=0))

    job = await SyncRunner(_Factory(destination), options=options).run(await _connection())

    assert job.status is JobStatus.FAILED and "rejected for good" in (job.error or "")
    assert destination.events.count("write-failed") == 1


async def test_a_cancelled_run_aborts() -> None:
    class Endless(FakeSource):
        async def read(
            self, catalog: ConfiguredCatalog, state: SyncState | None = None
        ) -> AsyncIterator[Record | State]:
            while True:
                await asyncio.sleep(0.01)
                yield Record(stream="a", data={"id": 1})

    destination = RecordingDestination()
    runner = SyncRunner(_Factory(destination, Endless.from_config({})))
    job = await runner.start(await _connection())
    await asyncio.sleep(0.05)
    assert await runner.cancel(job.id)
    assert (await runner.wait(job.id)).status is JobStatus.CANCELLED
    assert destination.events == ["begin", "abort:CancelledError"]


async def test_the_source_generator_is_closed_when_the_run_fails() -> None:
    closed: list[str] = []

    class Tracked(FakeSource):
        async def read(
            self, catalog: ConfiguredCatalog, state: SyncState | None = None
        ) -> AsyncIterator[Record | State]:
            try:
                for i in range(100):
                    yield Record(stream="a", data={"id": i})
            finally:
                closed.append("cursor")

    destination = RecordingDestination()
    destination.fail_with = DestinationWriteError("no")
    runner = SyncRunner(
        _Factory(destination, Tracked.from_config({})), options=SyncOptions(batch_size=2)
    )
    job = await runner.run(await _connection())
    assert job.status is JobStatus.FAILED
    # Closed by the runner before the job finished, not whenever the collector gets to it.
    assert closed == ["cursor"]


async def test_closing_batch_is_sent_only_to_destinations_that_ask(
    registry: ConnectorRegistry,
) -> None:
    class Marked(RecordingDestination):
        needs_final_batch = True

    marked = Marked()
    job = await SyncRunner(_Factory(marked), options=SyncOptions(batch_size=2)).run(
        await _connection(rows=4)
    )
    # 2 + 2, the State checkpoint has nothing left to flush, then the empty marker.
    assert [(b.size, b.is_last) for b in marked.batches] == [(2, False), (2, False), (0, True)]
    assert job.stats["a"].batches == 3

    plain = RecordingDestination()
    await SyncRunner(_Factory(plain), options=SyncOptions(batch_size=2)).run(
        await _connection(rows=4)
    )
    assert [(b.size, b.is_last) for b in plain.batches] == [(2, False), (2, False)]


# ---- hooks ------------------------------------------------------------------------------


async def test_status_hook_fires_on_status_changes_only(registry: ConnectorRegistry) -> None:
    statuses: list[JobStatus] = []
    steps: list[JobStatus] = []

    async def on_status(job: Job) -> None:
        statuses.append(job.status)

    async def on_progress(job: Job) -> None:
        steps.append(job.status)

    options = SyncOptions(batch_size=1, status_hook=on_status, progress_hook=on_progress)
    job = await SyncRunner(registry, options=options).run(await _connection(rows=4))

    assert job.status is JobStatus.SUCCEEDED
    assert statuses == [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.SUCCEEDED]
    assert len(steps) > len(statuses)  # once per batch as well


async def test_a_job_is_reported_as_pending_before_start_returns_and_a_refused_one_never(
    registry: ConnectorRegistry,
) -> None:
    reports: list[tuple[str, JobStatus]] = []

    async def on_status(job: Job) -> None:
        reports.append((job.id, job.status))

    runner = SyncRunner(registry, options=SyncOptions(status_hook=on_status))
    conn = await _connection()

    job = await runner.start(conn)
    # Known to the observer before the job's task has had a turn: what it reports
    # later (running, its final status) can only come after this.
    assert reports == [(job.id, JobStatus.PENDING)]

    with pytest.raises(SyncAlreadyRunningError):
        await runner.start(conn)
    assert reports == [(job.id, JobStatus.PENDING)], "a start that was refused reports nothing"

    await runner.wait(job.id)
    assert [status for _, status in reports] == [
        JobStatus.PENDING,
        JobStatus.RUNNING,
        JobStatus.SUCCEEDED,
    ]


async def test_a_start_cancelled_while_the_observer_runs_leaves_no_live_job(
    registry: ConnectorRegistry,
) -> None:
    told = asyncio.Event()

    async def slow_observer(job: Job) -> None:
        if job.status is JobStatus.PENDING:
            told.set()
            await asyncio.sleep(3600)

    store = InMemoryJobStore()
    runner = SyncRunner(registry, job_store=store, options=SyncOptions(status_hook=slow_observer))
    conn = await _connection()

    starting = asyncio.create_task(runner.start(conn))
    await told.wait()
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting

    # The job was stored, and nothing will ever execute it: it must not stay pending.
    [stored] = await store.list(conn.id)
    assert stored.status is JobStatus.CANCELLED and stored.finished_at is not None
    assert runner.active_job_id(conn.id) is None
    runner.options.status_hook = None
    assert (await runner.run(conn)).status is JobStatus.SUCCEEDED


async def test_a_failing_hook_does_not_fail_the_sync(registry: ConnectorRegistry) -> None:
    async def broken(job: Job) -> None:
        raise RuntimeError("metrics endpoint is down")

    options = SyncOptions(status_hook=broken, progress_hook=broken)
    job = await SyncRunner(registry, options=options).run(await _connection())
    assert job.status is JobStatus.SUCCEEDED and job.records_written == 5


# ---- one live job per connection ----------------------------------------------------


async def test_two_starts_in_one_process_cannot_both_win(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry)
    conn = await _connection()

    results = await asyncio.gather(runner.start(conn), runner.start(conn), return_exceptions=True)

    started = [r for r in results if isinstance(r, Job)]
    refused = [r for r in results if isinstance(r, SyncAlreadyRunningError)]
    assert len(started) == 1 and len(refused) == 1
    assert (await runner.wait(started[0].id)).status is JobStatus.SUCCEEDED


async def test_a_stale_job_is_failed_before_a_new_one_starts(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry, options=SyncOptions(stale_after_seconds=60))
    conn = await _connection()
    dead = await runner.job_store.create(
        Job(
            connection_id=conn.id,
            status=JobStatus.RUNNING,
            worker_id="gone",
            heartbeat_at=utcnow() - timedelta(hours=1),
        )
    )

    job = await runner.run(conn)

    assert job.status is JobStatus.SUCCEEDED
    stored = await runner.job_store.get(dead.id)
    assert stored is not None and stored.status is JobStatus.FAILED
    assert "stopped responding" in (stored.error or "")
    assert await runner.job_store.list_active(conn.id) == []


async def test_a_live_sibling_blocks_the_connection(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry)
    conn = await _connection()
    await runner.job_store.create(
        Job(
            connection_id=conn.id,
            status=JobStatus.RUNNING,
            worker_id="pod-b",
            heartbeat_at=utcnow(),
        )
    )
    with pytest.raises(SyncAlreadyRunningError) as exc:
        await runner.start(conn)
    assert exc.value.worker_id == "pod-b" and exc.value.connection_id == conn.id
    assert runner.active_job_id(conn.id) is None  # the reservation was given back


async def test_the_store_has_the_last_word_when_replicas_race(registry: ConnectorRegistry) -> None:
    class RacingStore(InMemoryJobStore):
        """A sibling inserts its job between this runner's check and its own insert."""

        async def create_exclusive(self, job: Job) -> Job | None:
            await super().create(
                Job(connection_id=job.connection_id, worker_id="pod-b", heartbeat_at=utcnow())
            )
            return await super().create_exclusive(job)

    store = RacingStore()
    assert isinstance(store, ExclusiveJobStore)
    runner = SyncRunner(registry, job_store=store)
    conn = await _connection()

    with pytest.raises(SyncAlreadyRunningError):
        await runner.start(conn)
    assert [j.worker_id for j in await store.list_active(conn.id)] == ["pod-b"]


async def test_exclusive_create_refuses_a_second_live_job() -> None:
    store = InMemoryJobStore()
    first = await store.create_exclusive(Job(connection_id="c"))
    assert first is not None
    assert await store.create_exclusive(Job(connection_id="c")) is None
    assert await store.create_exclusive(Job(connection_id="other")) is not None

    first.status = JobStatus.SUCCEEDED
    await store.update(first)
    assert await store.create_exclusive(Job(connection_id="c")) is not None


# ---- errors ---------------------------------------------------------------------------------


async def test_waiting_for_an_unknown_job(registry: ConnectorRegistry) -> None:
    with pytest.raises(JobNotFoundError):
        await SyncRunner(registry).wait("nope")


async def test_preflight_failure_is_reported_as_a_check_failure(
    registry: ConnectorRegistry,
) -> None:
    class Exploding(FakeSource):
        definition = ConnectorDefinition(
            name="exploding", display_name="E", kind=ConnectorKind.SOURCE
        )

        async def check(self) -> CheckResult:
            raise OSError("no route to host")

    registry.register(Exploding)
    # check() raised: check_connection() still answers.
    result = await Exploding.from_config({}).check_connection()
    assert result.ok is False and "no route to host" in (result.message or "")

    job = await SyncRunner(registry, options=SyncOptions(check_before_sync=True)).run(
        await _connection("exploding")
    )
    assert job.status is JobStatus.FAILED
    assert (job.error or "").startswith(f"{CheckFailedError.__name__}: source check failed")
    assert InMemoryDestination.batches == []


def test_missing_extra_names_what_to_install() -> None:
    with pytest.raises(MissingExtraError) as exc:
        require_extra("a_module_that_does_not_exist", extra="postgres", feature="postgres source")
    assert isinstance(exc.value, ImportError)
    assert str(exc.value) == (
        "postgres source requires the 'postgres' extra: pip install connector-py[postgres]"
    )
    assert require_extra("json", extra="core").dumps({}) == "{}"
