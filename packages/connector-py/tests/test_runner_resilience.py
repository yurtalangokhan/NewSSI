"""The runner when something around a sync fails: the job store, a cleanup, a caller that leaves."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest

from connector import (
    CheckResult,
    ConfiguredCatalog,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorRegistry,
    DestinationWriteError,
    InMemoryJobStore,
    Job,
    JobStatus,
    JobTakenOverError,
    Record,
    RetryPolicy,
    State,
    SyncOptions,
    SyncRunner,
    SyncState,
)
from connector.models import utcnow
from tests.conftest import FakeSource
from tests.test_runner_contract import RecordingDestination, _connection, _Factory

NO_DELAY = RetryPolicy(attempts=3, base_delay_seconds=0)


class _FlakyStore(InMemoryJobStore):
    """A job store whose ``update`` can be made to fail."""

    def __init__(self) -> None:
        super().__init__()
        self.down = False
        self.failing_terminal_updates = 0
        self.refused = 0

    async def update(self, job: Job) -> Job:
        if self.down or (job.is_terminal and self.failing_terminal_updates > 0):
            if job.is_terminal:
                self.failing_terminal_updates -= 1
            self.refused += 1
            raise ConnectionError("job store unreachable")
        return await super().update(job)


class _SlowWrites(RecordingDestination):
    """Every write waits, so a cancellation or a timeout lands in the destination."""

    def __init__(self, seconds: float = 30.0) -> None:
        super().__init__()
        self.seconds = seconds
        self.writing = asyncio.Event()

    async def write(self, batch: Any) -> Any:
        self.writing.set()
        await asyncio.sleep(self.seconds)
        return await super().write(batch)


class _FailingCleanup(FakeSource):
    """A source whose generator cannot be closed cleanly (a cursor on a dead connection)."""

    definition = ConnectorDefinition(
        name="failing_cleanup", display_name="F", kind=ConnectorKind.SOURCE
    )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        try:
            for i in range(1000):
                yield Record(stream="a", data={"id": i})
        finally:
            raise OSError("cursor.close(): connection is gone")


def _failing_cleanup() -> _FailingCleanup:
    return _FailingCleanup.from_config({})


# ---- A1: the job store fails while a job runs -------------------------------------------


async def test_a_heartbeat_the_store_refuses_does_not_end_the_job_or_keep_its_slot() -> None:
    store = _FlakyStore()

    class Stalling(FakeSource):
        """Nothing to flush for a while: only the heartbeat talks to the job store."""

        async def read(
            self, catalog: ConfiguredCatalog, state: SyncState | None = None
        ) -> AsyncIterator[Record | State]:
            store.down = True
            async with asyncio.timeout(2):
                while store.refused < 2:  # two beats in a row found the store down
                    await asyncio.sleep(0.001)
            store.down = False
            yield Record(stream="a", data={"id": 1})

    options = SyncOptions(heartbeat_interval_seconds=0.005, max_concurrent_jobs=1)
    runner = SyncRunner(
        _Factory(RecordingDestination(), Stalling.from_config({})), job_store=store, options=options
    )
    conn = await _connection()

    job = await runner.run(conn)

    assert job.status is JobStatus.SUCCEEDED and job.records_written == 1
    assert store.refused >= 2, "the heartbeat kept beating after the first refusal"
    assert (await store.get(job.id)).status is JobStatus.SUCCEEDED
    assert runner.active_job_id(conn.id) is None
    # The single slot is free again: a second job does not wait for ever.
    again = await asyncio.wait_for(runner.run(await _connection()), timeout=2)
    assert again.status is JobStatus.SUCCEEDED


async def test_the_final_status_is_stored_even_if_the_store_fails_once() -> None:
    store = _FlakyStore()
    store.failing_terminal_updates = 1
    statuses: list[JobStatus] = []

    async def on_status(job: Job) -> None:
        statuses.append(job.status)

    runner = SyncRunner(
        _Factory(RecordingDestination()),
        job_store=store,
        options=SyncOptions(retry=NO_DELAY, status_hook=on_status),
    )

    job = await runner.run(await _connection())

    assert job.status is JobStatus.SUCCEEDED and store.refused == 1
    assert (await store.get(job.id)).status is JobStatus.SUCCEEDED, "not left running in the store"
    assert statuses == [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.SUCCEEDED]


async def test_a_store_that_stays_down_at_the_end_still_frees_the_connection_and_the_slot() -> None:
    store = _FlakyStore()
    store.failing_terminal_updates = 100
    runner = SyncRunner(
        _Factory(RecordingDestination()),
        job_store=store,
        options=SyncOptions(retry=NO_DELAY, max_concurrent_jobs=1),
    )
    conn = await _connection()

    with pytest.raises(ConnectionError, match="job store unreachable"):
        await runner.run(conn)

    assert store.refused == NO_DELAY.attempts
    assert runner.active_job_id(conn.id) is None
    store.failing_terminal_updates = 0
    again = await asyncio.wait_for(runner.run(await _connection()), timeout=2)
    assert again.status is JobStatus.SUCCEEDED


async def test_a_background_job_whose_final_status_cannot_be_stored_is_logged_not_lost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Nobody awaits a ``start()`` task: an exception left on it surfaces only as
    # "Task exception was never retrieved" when the task is garbage collected.
    store = _FlakyStore()
    store.failing_terminal_updates = 100
    runner = SyncRunner(
        _Factory(RecordingDestination()), job_store=store, options=SyncOptions(retry=NO_DELAY)
    )
    conn = await _connection()

    with caplog.at_level("ERROR", logger="connector.sync"):
        job = await runner.start(conn)
        finished = await asyncio.wait_for(runner.wait(job.id), timeout=2)

    assert finished.status is JobStatus.SUCCEEDED  # the run itself was fine
    assert store.refused == NO_DELAY.attempts
    assert f"final status of background job {job.id}" in caplog.text
    assert runner.active_job_id(conn.id) is None


# ---- A2: the source's cleanup fails ----------------------------------------------------------


async def test_a_failing_source_cleanup_does_not_replace_the_reason_a_run_failed() -> None:
    destination = RecordingDestination()
    destination.fail_with = DestinationWriteError("disk full")
    runner = SyncRunner(
        _Factory(destination, _failing_cleanup()), options=SyncOptions(batch_size=2)
    )

    job = await runner.run(await _connection())

    assert job.status is JobStatus.FAILED
    assert job.error == "DestinationWriteError: disk full"
    assert destination.events == ["begin", "write-failed", "abort:DestinationWriteError"]


async def test_a_cancelled_run_ends_cancelled_although_the_source_cleanup_fails() -> None:
    destination = _SlowWrites()
    runner = SyncRunner(
        _Factory(destination, _failing_cleanup()), options=SyncOptions(batch_size=2)
    )
    job = await runner.start(await _connection())
    await destination.writing.wait()

    assert await runner.cancel(job.id)

    assert (await runner.wait(job.id)).status is JobStatus.CANCELLED
    assert destination.events == ["begin", "abort:CancelledError"]


async def test_a_shutdown_leaves_the_job_resumable_although_the_source_cleanup_fails() -> None:
    destination = _SlowWrites()
    runner = SyncRunner(
        _Factory(destination, _failing_cleanup()), options=SyncOptions(batch_size=2)
    )
    job = await runner.start(await _connection())
    await destination.writing.wait()

    assert await runner.shutdown() == 1

    stored = await runner.job_store.get(job.id)
    assert stored is not None and stored.status is JobStatus.RUNNING, (
        "terminal jobs are not resumed"
    )
    assert destination.events == ["begin", "abort:CancelledError"]


async def test_a_timed_out_run_says_so_although_the_source_cleanup_fails() -> None:
    destination = _SlowWrites()
    options = SyncOptions(batch_size=2, timeout_seconds=0.05)
    runner = SyncRunner(_Factory(destination, _failing_cleanup()), options=options)

    job = await runner.run(await _connection())

    assert job.status is JobStatus.FAILED and job.error == "timed out after 0.05s"
    assert destination.events == ["begin", "abort:CancelledError"]


class _SlowCheck(RecordingDestination):
    """A destination whose preflight check hangs (an unreachable store, a stuck DNS lookup)."""

    async def check(self) -> CheckResult:
        await asyncio.sleep(30)
        return CheckResult(ok=True)


async def test_the_timeout_covers_opening_and_checking_the_connectors() -> None:
    # Everything before the first record - the factory, ``open``, the preflight check -
    # is the job's time as much as the sync itself; without this, a check that hangs
    # keeps a RUNNING job with a fresh heartbeat forever.
    destination = _SlowCheck()
    options = SyncOptions(timeout_seconds=0.05, check_before_sync=True)
    runner = SyncRunner(_Factory(destination), options=options)

    job = await asyncio.wait_for(runner.run(await _connection()), timeout=5)

    assert job.status is JobStatus.FAILED and job.error == "timed out after 0.05s"
    assert destination.events == []  # never began
    assert destination.closed


async def test_a_job_declared_dead_by_a_sibling_does_not_come_back() -> None:
    # Worker A stalls (a long pause, a frozen VM): its heartbeat goes stale, sibling B
    # declares the job dead and takes the connection. When A goes on, its next heartbeat
    # must end its run instead of writing RUNNING back over B's verdict - otherwise two
    # jobs write the same connection and the cursor regresses.
    store = InMemoryJobStore()
    slow = _SlowWrites()
    a = SyncRunner(
        _Factory(slow),
        job_store=store,
        options=SyncOptions(batch_size=2, heartbeat_interval_seconds=0.02),
    )
    connection = await _connection()
    job_a = await a.start(connection)
    await slow.writing.wait()  # A is inside a write that never ends

    sink = RecordingDestination()
    b = SyncRunner(
        _Factory(sink), job_store=store, options=SyncOptions(batch_size=2, stale_after_seconds=0)
    )
    job_b = await b.run(connection)  # A is stale to B: failed, then B runs the connection

    ended = await asyncio.wait_for(a.wait(job_a.id), timeout=5)
    assert ended.status is JobStatus.FAILED and "superseded" in (ended.error or "")
    stored = await store.get(job_a.id)
    assert stored is not None and stored.status is JobStatus.FAILED
    assert job_b.status is JobStatus.SUCCEEDED and len(sink.batches) == 3
    assert slow.events == ["begin", "abort:CancelledError"]


async def test_the_store_refuses_to_revive_a_terminal_job() -> None:
    store = InMemoryJobStore()
    job = Job(connection_id="c1", status=JobStatus.RUNNING)
    await store.create(job)
    ended = job.model_copy(update={"status": JobStatus.FAILED, "error": "dead"})
    await store.update(ended)
    with pytest.raises(JobTakenOverError):
        await store.update(job)  # RUNNING over FAILED
    assert (await store.get(job.id)).status is JobStatus.FAILED
    await store.update(ended.model_copy(update={"status": JobStatus.CANCELLED}))  # terminal: fine


async def test_the_in_memory_job_store_keeps_a_bounded_history() -> None:
    # The default store of a long-running process: finished jobs must not pile up forever.
    store = InMemoryJobStore(max_finished_jobs=3)
    live = Job(connection_id="live", status=JobStatus.RUNNING)
    await store.create(live)
    done: list[Job] = []
    for i in range(5):
        job = Job(connection_id=f"c{i}", status=JobStatus.RUNNING)
        await store.create(job)
        await store.update(job.model_copy(update={"status": JobStatus.SUCCEEDED}))
        done.append(job)

    history = await store.list(limit=100)
    assert {j.connection_id for j in history if j.is_terminal} == {"c2", "c3", "c4"}
    assert await store.get(done[0].id) is None and await store.get(done[4].id) is not None
    assert (await store.get(live.id)).status is JobStatus.RUNNING  # live jobs are never evicted


# ---- A5: a job that is stopped before its task had a turn ---------------------------------


async def test_cancelling_a_job_before_its_first_step_closes_it(
    registry: ConnectorRegistry,
) -> None:
    reports: list[JobStatus] = []

    async def on_status(job: Job) -> None:
        reports.append(job.status)

    runner = SyncRunner(registry, options=SyncOptions(status_hook=on_status))
    conn = await _connection()
    job = await runner.start(conn)

    assert await runner.cancel(job.id)  # no await in between: the task never ran

    assert (await runner.wait(job.id)).status is JobStatus.CANCELLED
    assert reports == [JobStatus.PENDING, JobStatus.CANCELLED]
    assert await runner.job_store.list_active(conn.id) == []
    assert runner.active_job_id(conn.id) is None
    assert (await runner.run(conn)).status is JobStatus.SUCCEEDED


async def test_a_shutdown_before_the_first_step_frees_the_connection_and_keeps_the_job(
    registry: ConnectorRegistry,
) -> None:
    runner = SyncRunner(registry)
    conn = await _connection()
    job = await runner.start(conn)

    assert await runner.shutdown() == 1

    assert runner.active_job_id(conn.id) is None
    stored = await runner.job_store.get(job.id)
    assert stored is not None and stored.status is JobStatus.PENDING  # the next start resumes it
    successor = SyncRunner(registry, job_store=runner.job_store)
    assert [j.id for j in await successor.recover_interrupted()] == [job.id]


# ---- A9: jobs this runner closes for a worker that is gone ---------------------------------


async def test_observers_hear_about_jobs_closed_for_a_dead_worker(
    registry: ConnectorRegistry,
) -> None:
    reports: list[tuple[str, JobStatus]] = []
    steps: list[str] = []

    async def on_status(job: Job) -> None:
        reports.append((job.id, job.status))

    async def on_progress(job: Job) -> None:
        steps.append(job.id)

    options = SyncOptions(stale_after_seconds=60, status_hook=on_status, progress_hook=on_progress)
    runner = SyncRunner(registry, options=options)
    conn = await _connection()
    long_ago = utcnow() - timedelta(hours=1)
    stale = await runner.job_store.create(
        Job(
            connection_id=conn.id, status=JobStatus.RUNNING, worker_id="gone", heartbeat_at=long_ago
        )
    )

    job = await runner.run(conn)  # takes the connection over

    assert reports[:2] == [(stale.id, JobStatus.FAILED), (job.id, JobStatus.PENDING)]
    assert stale.id in steps
    # The record of when it last gave a sign of life is not overwritten by closing it.
    assert (await runner.job_store.get(stale.id)).heartbeat_at == long_ago

    orphan = await runner.job_store.create(Job(connection_id="other", status=JobStatus.PENDING))
    assert [j.id for j in await runner.recover_interrupted()] == [orphan.id]
    assert reports[-1] == (orphan.id, JobStatus.FAILED)


# ---- A11: a timeout that is not the job's ---------------------------------------------------


@pytest.mark.parametrize("limit", [None, 60.0])
async def test_a_timeout_raised_by_the_source_is_not_blamed_on_the_job_limit(
    limit: float | None,
) -> None:
    class Impatient(FakeSource):
        async def read(
            self, catalog: ConfiguredCatalog, state: SyncState | None = None
        ) -> AsyncIterator[Record | State]:
            yield Record(stream="a", data={"id": 1})
            raise TimeoutError("read timed out after 30s")

    runner = SyncRunner(
        _Factory(RecordingDestination(), Impatient.from_config({})),
        options=SyncOptions(timeout_seconds=limit),
    )

    job = await runner.run(await _connection())

    assert job.status is JobStatus.FAILED
    assert job.error == "TimeoutError: read timed out after 30s"


# ---- A12: smaller promises -------------------------------------------------------------------


async def test_recovery_leaves_a_job_this_runner_executes_through_run() -> None:
    destination = _SlowWrites(seconds=0.05)
    runner = SyncRunner(_Factory(destination), options=SyncOptions(batch_size=5))
    running = asyncio.create_task(runner.run(await _connection()))
    await destination.writing.wait()

    assert await runner.recover_interrupted() == []

    assert (await running).status is JobStatus.SUCCEEDED


async def test_a_waiter_that_is_cancelled_does_not_take_the_job_with_it() -> None:
    destination = _SlowWrites(seconds=0.05)
    runner = SyncRunner(_Factory(destination), options=SyncOptions(batch_size=5))
    job = await runner.start(await _connection())
    waiter = asyncio.create_task(runner.wait(job.id))
    await destination.writing.wait()

    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert (await runner.wait(job.id)).status is JobStatus.SUCCEEDED


async def test_a_close_that_fails_after_a_complete_sync_does_not_fail_the_job() -> None:
    class Unclosable(RecordingDestination):
        async def close(self) -> None:
            raise RuntimeError("pool already closed")

    destination = Unclosable()

    job = await SyncRunner(_Factory(destination)).run(await _connection())

    assert job.status is JobStatus.SUCCEEDED and job.error is None
    assert destination.events == ["begin", "finalize"]


async def test_preview_closes_the_stream_it_stopped_reading() -> None:
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

    rows = await Tracked.from_config({}).preview("a", limit=2)

    # Closed by preview itself, not by the garbage collector after the source is gone.
    assert len(rows) == 2 and closed == ["cursor"]


# ---- A13: abort paths that had no test --------------------------------------------------------


async def test_a_failing_finalize_aborts_the_run() -> None:
    class NoFinalize(RecordingDestination):
        async def finalize(self, catalog: Any, connection_id: str | None = None, *, job_id=None):
            self.events.append("finalize-failed")
            raise ConnectionError("commit failed")

    destination = NoFinalize()

    job = await SyncRunner(_Factory(destination)).run(await _connection())

    assert job.status is JobStatus.FAILED and job.error == "ConnectionError: commit failed"
    assert destination.events == ["begin", "finalize-failed", "abort:ConnectionError"]
    assert destination.closed


class _CancelOnClose(FakeSource):
    """aiokafka 0.14's idle consumer: ``stop()`` lets out a CancelledError that is not ours."""

    definition = ConnectorDefinition(
        name="cancel_on_close", display_name="C", kind=ConnectorKind.SOURCE
    )

    async def close(self) -> None:
        raise asyncio.CancelledError


async def test_a_spurious_cancellation_from_a_connector_close_does_not_cancel_the_job() -> None:
    # Seen live: the job was stored as "cancelled" and runner.run() raised CancelledError
    # although nothing had cancelled the run; closing is not part of the sync's outcome.
    destination = RecordingDestination()
    source = _CancelOnClose.from_config({"rows": 3})
    runner = SyncRunner(_Factory(destination, source=source), job_store=InMemoryJobStore())

    job = await runner.run(await _connection(rows=3))

    assert job.status is JobStatus.SUCCEEDED and job.error is None
