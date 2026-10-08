from __future__ import annotations

import asyncio

import pytest

from connector import (
    ConfiguredCatalog,
    Connection,
    ConnectorRegistry,
    DestinationSyncMode,
    InMemoryStateStore,
    JobStatus,
    RetryPolicy,
    SyncMode,
    SyncOptions,
    SyncRunner,
)
from connector.destinations.memory import InMemoryDestination
from tests.conftest import FakeSource


async def _connection(
    rows: int = 7, streams: list[str] | None = None, incremental: bool = False
) -> Connection:
    streams = streams or ["a"]
    src = FakeSource.from_config({"rows": rows, "streams": streams})
    catalog = ConfiguredCatalog.from_catalog(
        await src.discover(),
        sync_mode=SyncMode.INCREMENTAL if incremental else SyncMode.FULL_REFRESH,
        destination_sync_mode=DestinationSyncMode.OVERWRITE,
    )
    return Connection(
        name="t",
        source_name="fake",
        source_config={"rows": rows, "streams": streams},
        destination_name="memory",
        destination_config={},
        catalog=catalog,
    )


async def test_full_refresh_batches_and_stats(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry, options=SyncOptions(batch_size=3))
    job = await runner.run(await _connection(rows=7))

    assert job.status is JobStatus.SUCCEEDED
    assert job.records_read == 7 and job.records_written == 7
    # 3 + 3, then the source's State checkpoint forces a flush of the remaining 1.
    # Nothing is left to close the stream with, and this destination does not ask
    # for an empty closing batch.
    assert job.stats["a"].batches == 3
    sizes = [b.size for b in InMemoryDestination.batches]
    assert sizes == [3, 3, 1]
    assert [b.batch_index for b in InMemoryDestination.batches] == [0, 1, 2]
    assert {b.job_id for b in InMemoryDestination.batches} == {job.id}
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == list(range(1, 8))


async def test_empty_stream_writes_nothing(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry)
    job = await runner.run(await _connection(rows=0))
    assert job.status is JobStatus.SUCCEEDED
    assert InMemoryDestination.batches == []
    assert InMemoryDestination.events == [("begin", job.id), ("finalize", job.id)]


async def test_multiple_streams_are_batched_independently(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry, options=SyncOptions(batch_size=2))
    job = await runner.run(await _connection(rows=3, streams=["a", "b"]))
    assert job.status is JobStatus.SUCCEEDED
    assert set(InMemoryDestination.sink) == {"a", "b"}
    assert all(len(v) == 3 for v in InMemoryDestination.sink.values())
    assert all(b.stream in {"a", "b"} for b in InMemoryDestination.batches)


async def test_incremental_uses_state_store(registry: ConnectorRegistry) -> None:
    store = InMemoryStateStore()
    runner = SyncRunner(registry, state_store=store)
    conn = await _connection(rows=4, incremental=True)

    first = await runner.run(conn)
    assert first.records_read == 4
    assert (await store.load(conn.id)).get("a") == {"cursor": 4}

    InMemoryDestination.reset()
    second = await runner.run(conn)
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == [5, 6, 7, 8]
    assert (await store.load(conn.id)).get("a") == {"cursor": 8}

    InMemoryDestination.reset()
    third = await runner.run(conn, full_refresh=True)
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == [1, 2, 3, 4]
    assert second.status is third.status is JobStatus.SUCCEEDED


async def test_a_full_refresh_forgets_the_saved_checkpoints_before_it_reads(
    registry: ConnectorRegistry,
) -> None:
    store = InMemoryStateStore()
    runner = SyncRunner(
        registry,
        state_store=store,
        options=SyncOptions(retry=RetryPolicy(attempts=2, base_delay_seconds=0.001)),
    )
    conn = await _connection(rows=4, incremental=True)
    assert (await runner.run(conn)).status is JobStatus.SUCCEEDED
    assert (await store.load(conn.id)).get("a") == {"cursor": 4}

    # Even a full refresh that fails leaves no cursor behind: "start over" was asked
    # for, so the next run reads from the beginning as well.
    InMemoryDestination.reset()
    conn.destination_config = {"fail_first_n_batches": 5}
    failed = await runner.run(conn, full_refresh=True)
    assert failed.status is JobStatus.FAILED
    assert (await store.load(conn.id)).streams == {}


async def test_the_memory_destination_keeps_a_bounded_window(
    registry: ConnectorRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A process that keeps dry-running must not accumulate every record ever written.
    monkeypatch.setattr(InMemoryDestination, "max_records_per_stream", 5)
    monkeypatch.setattr(InMemoryDestination, "max_batches", 2)
    runner = SyncRunner(registry, options=SyncOptions(batch_size=3))
    await runner.run(await _connection(rows=8))
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == [4, 5, 6, 7, 8]
    assert [b.batch_index for b in InMemoryDestination.batches] == [1, 2]
    assert [e for e, _ in InMemoryDestination.events] == ["begin", "finalize"]


async def test_retry_then_success(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(
        registry,
        options=SyncOptions(batch_size=10, retry=RetryPolicy(attempts=3, base_delay_seconds=0.001)),
    )
    conn = await _connection(rows=2)
    conn.destination_config = {"fail_first_n_batches": 2}
    job = await runner.run(conn)
    assert job.status is JobStatus.SUCCEEDED
    assert job.records_written == 2


async def test_retry_exhausted_fails_job(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(
        registry,
        options=SyncOptions(retry=RetryPolicy(attempts=2, base_delay_seconds=0.001)),
    )
    conn = await _connection(rows=2)
    conn.destination_config = {"fail_first_n_batches": 5}
    job = await runner.run(conn)
    assert job.status is JobStatus.FAILED
    assert "DestinationWriteError" in (job.error or "")
    assert (await runner.job_store.get(job.id)) is not None
    assert (await runner.job_store.get(job.id)).status is JobStatus.FAILED


async def test_hidden_connector_blocks_sync(registry: ConnectorRegistry) -> None:
    registry.set_enabled("fake", False)
    runner = SyncRunner(registry)
    conn = await _connection(rows=1)
    # The job is recorded as FAILED (with the reason) instead of raising, so background
    # runs and scheduled runs leave a trace in the job store.
    job = await runner.run(conn)
    assert job.status is JobStatus.FAILED
    assert "ConnectorDisabledError" in (job.error or "")
    assert runner.active_job_id(conn.id) is None


async def test_background_start_wait_and_progress_hook(registry: ConnectorRegistry) -> None:
    seen: list[JobStatus] = []

    async def hook(job) -> None:  # noqa: ANN001
        seen.append(job.status)

    runner = SyncRunner(registry, options=SyncOptions(batch_size=2, progress_hook=hook))
    job = await runner.start(await _connection(rows=5))
    assert job.status is JobStatus.PENDING
    done = await runner.wait(job.id)
    assert done.status is JobStatus.SUCCEEDED
    assert seen[0] is JobStatus.RUNNING and seen[-1] is JobStatus.SUCCEEDED
    assert (await runner.job_store.list(connection_id=job.connection_id))[0].id == job.id


async def test_cancel_running_job(registry: ConnectorRegistry) -> None:
    runner = SyncRunner(registry, options=SyncOptions(batch_size=1))
    conn = await _connection(rows=100_000)
    job = await runner.start(conn)
    await asyncio.sleep(0.01)
    assert await runner.cancel(job.id)
    final = await runner.wait(job.id)
    assert final.status is JobStatus.CANCELLED
