"""Job guards: one job per connection, concurrency limit, timeout, preflight check, recovery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from connector import (
    CheckResult,
    ConfiguredCatalog,
    Connection,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorRegistry,
    Job,
    JobStatus,
    Record,
    State,
    SyncAlreadyRunningError,
    SyncOptions,
    SyncRunner,
    SyncState,
)
from tests.conftest import FakeSource


class SlowSource(FakeSource):
    definition = ConnectorDefinition(name="slow", display_name="Slow", kind=ConnectorKind.SOURCE)

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        for i in range(self.config.rows):
            await asyncio.sleep(0.02)
            yield Record(stream="a", data={"id": i})


class BrokenCheckSource(FakeSource):
    definition = ConnectorDefinition(name="broken", display_name="B", kind=ConnectorKind.SOURCE)

    async def check(self) -> CheckResult:
        return CheckResult(ok=False, message="cannot connect")


async def _conn(source: str, rows: int = 3) -> Connection:
    src = FakeSource.from_config({"rows": rows})
    return Connection(
        name="c",
        source_name=source,
        source_config={"rows": rows},
        destination_name="memory",
        destination_config={},
        catalog=ConfiguredCatalog.from_catalog(await src.discover()),
    )


async def test_one_job_per_connection(registry: ConnectorRegistry) -> None:
    registry.register(SlowSource)
    runner = SyncRunner(registry)
    conn = await _conn("slow", rows=20)
    first = await runner.start(conn)
    await asyncio.sleep(0.01)
    assert runner.active_job_id(conn.id) == first.id
    with pytest.raises(SyncAlreadyRunningError, match="already being synced by job"):
        await runner.start(conn)
    await runner.cancel(first.id)
    await runner.wait(first.id)
    assert runner.active_job_id(conn.id) is None
    second = await runner.run(conn)  # allowed again once the first is finished
    assert second.status is JobStatus.SUCCEEDED


async def test_concurrent_jobs_can_be_allowed(registry: ConnectorRegistry) -> None:
    registry.register(SlowSource)
    runner = SyncRunner(registry, options=SyncOptions(allow_concurrent_jobs=True))
    conn = await _conn("slow", rows=5)
    a = await runner.start(conn)
    b = await runner.start(conn)
    assert (await runner.wait(a.id)).status is JobStatus.SUCCEEDED
    assert (await runner.wait(b.id)).status is JobStatus.SUCCEEDED


async def test_concurrency_limit_keeps_extra_jobs_pending(registry: ConnectorRegistry) -> None:
    registry.register(SlowSource)
    seen: list[tuple[str, JobStatus]] = []

    async def hook(job: Job) -> None:
        seen.append((job.connection_id, job.status))

    runner = SyncRunner(registry, options=SyncOptions(max_concurrent_jobs=1, progress_hook=hook))
    first_conn, second_conn = await _conn("slow", rows=3), await _conn("slow", rows=3)
    first = await runner.start(first_conn)
    second = await runner.start(second_conn)
    await asyncio.sleep(0.03)
    assert (await runner.job_store.get(first.id)).status is JobStatus.RUNNING
    waiting = await runner.job_store.get(second.id)
    assert waiting.status is JobStatus.PENDING and waiting.started_at is None

    assert (await runner.wait(first.id)).status is JobStatus.SUCCEEDED
    assert (await runner.wait(second.id)).status is JobStatus.SUCCEEDED
    # The second connection reports nothing until the first one has finished.
    first_done = seen.index((first_conn.id, JobStatus.SUCCEEDED))
    assert all(conn_id == first_conn.id for conn_id, _ in seen[: first_done + 1])


async def test_cancelling_a_waiting_job_frees_nothing_it_never_held(
    registry: ConnectorRegistry,
) -> None:
    registry.register(SlowSource)
    runner = SyncRunner(registry, options=SyncOptions(max_concurrent_jobs=1))
    first = await runner.start(await _conn("slow", rows=5))
    second = await runner.start(await _conn("slow", rows=5))
    await asyncio.sleep(0.01)
    assert await runner.cancel(second.id)
    assert (await runner.wait(second.id)).status is JobStatus.CANCELLED
    assert (await runner.wait(first.id)).status is JobStatus.SUCCEEDED
    third = await runner.run(await _conn("slow", rows=1))  # the single slot is still usable
    assert third.status is JobStatus.SUCCEEDED


async def test_shutdown_leaves_jobs_resumable(registry: ConnectorRegistry) -> None:
    registry.register(SlowSource)
    runner = SyncRunner(registry, options=SyncOptions(max_concurrent_jobs=1))
    running = await runner.start(await _conn("slow", rows=50))
    waiting = await runner.start(await _conn("slow", rows=50))
    await asyncio.sleep(0.03)

    assert await runner.shutdown() == 2

    # Not CANCELLED: the process stopped, nobody asked for the work to stop.
    assert (await runner.job_store.get(running.id)).status is JobStatus.RUNNING
    assert (await runner.job_store.get(waiting.id)).status is JobStatus.PENDING
    successor = SyncRunner(registry, job_store=runner.job_store)
    recovered = await successor.recover_interrupted()
    assert {job.id for job in recovered} == {running.id, waiting.id}


async def test_job_timeout(registry: ConnectorRegistry) -> None:
    registry.register(SlowSource)
    runner = SyncRunner(registry, options=SyncOptions(timeout_seconds=0.05))
    job = await runner.run(await _conn("slow", rows=50))
    assert job.status is JobStatus.FAILED
    assert "timed out" in (job.error or "")
    assert runner.active_job_id(job.connection_id) is None


async def test_preflight_check_blocks_sync(registry: ConnectorRegistry) -> None:
    registry.register(BrokenCheckSource)
    runner = SyncRunner(registry, options=SyncOptions(check_before_sync=True))
    job = await runner.run(await _conn("broken"))
    assert job.status is JobStatus.FAILED
    assert "source check failed: cannot connect" in (job.error or "")
    assert job.records_read == 0

    ok = await SyncRunner(registry, options=SyncOptions(check_before_sync=True)).run(
        await _conn("fake")
    )
    assert ok.status is JobStatus.SUCCEEDED


async def test_recover_stale_jobs(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry)
    # Simulate jobs left behind by a crashed process.
    stale_running = await runner.job_store.create(Job(connection_id="x", status=JobStatus.RUNNING))
    stale_pending = await runner.job_store.create(Job(connection_id="y", status=JobStatus.PENDING))
    done = await runner.job_store.create(Job(connection_id="z", status=JobStatus.SUCCEEDED))

    assert len(await runner.recover_interrupted()) == 2
    assert (await runner.job_store.get(stale_running.id)).status is JobStatus.FAILED
    assert "restart" in (await runner.job_store.get(stale_pending.id)).error
    assert (await runner.job_store.get(done.id)).status is JobStatus.SUCCEEDED
    assert await runner.recover_interrupted() == []
