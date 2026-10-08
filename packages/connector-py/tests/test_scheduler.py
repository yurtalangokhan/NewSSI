"""Durable scheduler: cron + interval, misfires, replica safety, restart behaviour."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from connector import (
    ConfiguredCatalog,
    Connection,
    ConnectorRegistry,
    InMemoryConnectionStore,
    InMemoryJobStore,
    InMemoryScheduleStore,
    Job,
    JobStatus,
    JobTrigger,
    Schedule,
    SyncOptions,
    SyncRunner,
    SyncScheduler,
    next_run_at,
)
from tests.conftest import FakeSource

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


async def _connection(schedule: Schedule | None, name: str = "c") -> Connection:
    src = FakeSource.from_config({"rows": 2})
    return Connection(
        name=name,
        source_name="fake",
        source_config={"rows": 2},
        destination_name="memory",
        destination_config={},
        catalog=ConfiguredCatalog.from_catalog(await src.discover()),
        schedule=schedule,
    )


async def _finish(runner: SyncRunner, jobs: list[Job]) -> list[Job]:
    return [await runner.wait(j.id) for j in jobs]


# ---------------------------------------------------------------------------
# Schedule model
# ---------------------------------------------------------------------------


def test_schedule_is_cron_or_interval_but_not_both() -> None:
    assert Schedule.every(minutes=30).interval_seconds == 1800
    assert Schedule.every(hours=1, minutes=30, seconds=5).interval_seconds == 5405
    assert Schedule.cron("0 3 * * *", "Europe/Istanbul").cron_expression == "0 3 * * *"
    with pytest.raises(ValidationError):
        Schedule()
    with pytest.raises(ValidationError):
        Schedule(cron_expression="* * * * *", interval_seconds=60)
    a, b = Schedule.every(minutes=5), Schedule.every(minutes=10)
    assert a.fingerprint() != b.fingerprint()
    assert a.fingerprint() == Schedule.every(seconds=300).fingerprint()


def test_next_run_at_for_interval_and_cron_with_timezone() -> None:
    assert next_run_at(Schedule.every(minutes=15), T0) == T0 + timedelta(minutes=15)
    pytest.importorskip("croniter")
    nxt = next_run_at(Schedule.cron("0 15 * * *", "Europe/Istanbul"), T0)
    # 15:00 Istanbul (UTC+3) == 12:00 UTC, which is not strictly after T0 -> next day
    assert nxt == datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    with pytest.raises(Exception):  # noqa: B017 - croniter raises its own error type
        next_run_at(Schedule.cron("not a cron"))


# ---------------------------------------------------------------------------
# ticking
# ---------------------------------------------------------------------------


async def test_interval_runs_when_due_and_advances_without_drift(
    registry: ConnectorRegistry,
) -> None:
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(Schedule.every(minutes=10)))
    runner = SyncRunner(registry)
    sched = SyncScheduler(runner, connections, poll_interval_seconds=15)

    entry = await sched.schedule(conn, now=T0)
    assert entry is not None and entry.next_run_at == T0 + timedelta(minutes=10)
    assert await sched.tick(T0 + timedelta(minutes=9)) == []

    late = T0 + timedelta(minutes=10, seconds=7)  # the poll came 7s after the slot
    jobs = await _finish(runner, await sched.tick(late))
    assert [j.status for j in jobs] == [JobStatus.SUCCEEDED]
    assert jobs[0].trigger is JobTrigger.SCHEDULE
    after = await sched.schedules.get(conn.id)
    assert after.next_run_at == T0 + timedelta(minutes=20)  # from the slot, not from "late"
    assert after.last_job_id == jobs[0].id and after.last_run_at == late
    assert await sched.tick(late) == []  # same slot is never run twice


async def test_run_on_create_fires_immediately(registry: ConnectorRegistry) -> None:
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(Schedule.every(hours=1, run_on_create=True)))
    runner = SyncRunner(registry)
    sched = SyncScheduler(runner, connections)
    await sched.schedule(conn, now=T0)
    assert len(await _finish(runner, await sched.tick(T0))) == 1


async def test_editing_the_schedule_resets_the_slot_but_other_edits_do_not(
    registry: ConnectorRegistry,
) -> None:
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(Schedule.every(minutes=10)))
    sched = SyncScheduler(SyncRunner(registry), connections)
    first = await sched.schedule(conn, now=T0)

    conn.name = "renamed"
    same = await sched.schedule(conn, now=T0 + timedelta(minutes=5))
    assert same.next_run_at == first.next_run_at  # unrelated edit keeps the slot

    conn.schedule = Schedule.every(minutes=30)
    moved = await sched.schedule(conn, now=T0 + timedelta(minutes=5))
    assert moved.next_run_at == T0 + timedelta(minutes=35)

    conn.schedule = Schedule.every(minutes=30, enabled=False)
    assert await sched.schedule(conn) is None and await sched.schedules.get(conn.id) is None


async def test_misfire_policy_after_downtime(registry: ConnectorRegistry) -> None:
    async def scheduler(policy: str) -> tuple[SyncScheduler, SyncRunner, Connection]:
        connections = InMemoryConnectionStore()
        conn = await connections.create(await _connection(Schedule.every(minutes=10)))
        runner = SyncRunner(registry)
        sched = SyncScheduler(runner, connections, misfire=policy)  # type: ignore[arg-type]
        await sched.schedule(conn, now=T0)
        return sched, runner, conn

    back_online = T0 + timedelta(hours=3)  # the service was down for three hours

    sched, runner, conn = await scheduler("run_once")
    jobs = await _finish(runner, await sched.tick(back_online))
    assert len(jobs) == 1  # one catch-up run, not eighteen
    assert (await sched.schedules.get(conn.id)).next_run_at == back_online + timedelta(minutes=10)

    sched, runner, conn = await scheduler("skip")
    assert await sched.tick(back_online) == []
    assert (await sched.schedules.get(conn.id)).next_run_at == back_online + timedelta(minutes=10)


async def test_two_replicas_share_a_store_and_only_one_runs_the_slot(
    registry: ConnectorRegistry,
) -> None:
    connections, schedules, jobs = (
        InMemoryConnectionStore(),
        InMemoryScheduleStore(),
        InMemoryJobStore(),
    )
    conn = await connections.create(await _connection(Schedule.every(minutes=10)))
    runner_a = SyncRunner(registry, job_store=jobs, worker_id="a")
    runner_b = SyncRunner(registry, job_store=jobs, worker_id="b")
    replica_a = SyncScheduler(runner_a, connections, schedules)
    replica_b = SyncScheduler(runner_b, connections, schedules)
    await replica_a.schedule(conn, now=T0)

    due = T0 + timedelta(minutes=10)
    started = await asyncio.gather(replica_a.tick(due), replica_b.tick(due))
    assert sorted(len(s) for s in started) == [0, 1]
    assert len(await jobs.list(conn.id)) == 1


async def test_connection_deleted_or_unscheduled_is_cleaned_up(
    registry: ConnectorRegistry,
) -> None:
    connections = InMemoryConnectionStore()
    keep = await connections.create(await _connection(Schedule.every(minutes=5), "keep"))
    gone = await connections.create(await _connection(Schedule.every(minutes=5), "gone"))
    sched = SyncScheduler(SyncRunner(registry), connections)
    assert await sched.sync_schedules() == 2

    await connections.delete(gone.id)
    assert await sched.sync_schedules() == 1
    assert set(await sched.next_runs()) == {keep.id}
    await sched.unschedule(keep.id)
    assert await sched.next_runs() == {}


async def test_background_loop_starts_and_stops(registry: ConnectorRegistry) -> None:
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(Schedule.every(hours=1, run_on_create=True)))
    runner = SyncRunner(registry)
    sched = SyncScheduler(runner, connections, poll_interval_seconds=0.01)
    await sched.start()
    assert sched.running
    for _ in range(100):
        await asyncio.sleep(0.01)
        if (await sched.schedules.get(conn.id)).last_job_id:
            break
    entry = await sched.schedules.get(conn.id)
    assert entry.last_job_id is not None
    assert (await runner.wait(entry.last_job_id)).status is JobStatus.SUCCEEDED
    await sched.stop()
    assert not sched.running


async def test_polling_recovers_a_job_whose_worker_died_later(registry: ConnectorRegistry) -> None:
    """With ``stale_after_seconds`` the dead-job check repeats on every poll."""
    jobs = InMemoryJobStore()
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(None))
    runner = SyncRunner(registry, job_store=jobs)
    sched = SyncScheduler(runner, connections, poll_interval_seconds=0.01, stale_after_seconds=60)
    assert await sched.start() == []
    try:
        # A sibling replica dies after this one started: its job stops beating.
        orphan = await jobs.create(
            Job(
                connection_id=conn.id,
                status=JobStatus.RUNNING,
                worker_id="dead-sibling",
                heartbeat_at=datetime.now(UTC) - timedelta(minutes=5),
            )
        )
        for _ in range(100):
            await asyncio.sleep(0.01)
            if (await jobs.get(orphan.id)).status is JobStatus.FAILED:
                break
        assert (await jobs.get(orphan.id)).status is JobStatus.FAILED
        resumed = [j for j in await jobs.list(conn.id) if j.trigger is JobTrigger.RESUME]
        assert len(resumed) == 1
        assert (await runner.wait(resumed[0].id)).status is JobStatus.SUCCEEDED
    finally:
        await sched.stop()


async def test_a_connection_that_cannot_be_loaded_does_not_starve_the_others(
    registry: ConnectorRegistry,
) -> None:
    class FlakyConnections(InMemoryConnectionStore):
        broken: str | None = None

        async def get(self, connection_id: str) -> Connection | None:
            if connection_id == self.broken:
                raise RuntimeError("configuration store is unreachable")
            return await super().get(connection_id)

    connections = FlakyConnections()
    bad = await connections.create(await _connection(Schedule.every(minutes=5), "bad"))
    good = await connections.create(await _connection(Schedule.every(minutes=5), "good"))
    runner = SyncRunner(registry)
    sched = SyncScheduler(runner, connections)
    await sched.schedule(bad, now=T0)
    await sched.schedule(good, now=T0 + timedelta(seconds=1))
    connections.broken = bad.id

    started = await sched.tick(T0 + timedelta(minutes=6))

    assert [job.connection_id for job in started] == [good.id]
    # The broken one keeps its slot, so it runs as soon as it can be loaded again.
    assert (await sched.next_runs())[bad.id] == T0 + timedelta(minutes=5)
    await _finish(runner, started)


async def test_an_unschedulable_connection_does_not_stop_the_scheduler(
    registry: ConnectorRegistry,
) -> None:
    pytest.importorskip("croniter")
    connections = InMemoryConnectionStore()
    bad = await connections.create(await _connection(Schedule.cron("not a cron"), "bad"))
    good = await connections.create(await _connection(Schedule.every(minutes=5), "good"))
    sched = SyncScheduler(SyncRunner(registry), connections, poll_interval_seconds=3600)

    await sched.start()
    try:
        assert sched.running
        runs = await sched.next_runs()
        assert good.id in runs and bad.id not in runs
    finally:
        await sched.stop()


async def test_one_connection_that_cannot_be_resumed_does_not_stop_the_others(
    registry: ConnectorRegistry,
) -> None:
    class FlakyConnections(InMemoryConnectionStore):
        broken: str | None = None

        async def get(self, connection_id: str) -> Connection | None:
            if connection_id == self.broken:
                raise RuntimeError("configuration store is unreachable")
            return await super().get(connection_id)

    jobs = InMemoryJobStore()
    connections = FlakyConnections()
    bad = await connections.create(await _connection(None, "bad"))
    good = await connections.create(await _connection(None, "good"))
    for conn in (bad, good):  # both were running when the previous process went away
        await jobs.create(
            Job(connection_id=conn.id, status=JobStatus.RUNNING, worker_id="previous")
        )
    connections.broken = bad.id
    runner = SyncRunner(registry, job_store=jobs)
    sched = SyncScheduler(runner, connections, poll_interval_seconds=3600)

    resumed = await sched.start()
    try:
        assert [job.connection_id for job in resumed] == [good.id]
        assert resumed[0].trigger is JobTrigger.RESUME
        assert sched.running, "a resume that failed must not leave the scheduler without its loop"
        await _finish(runner, resumed)
    finally:
        await sched.stop()


async def test_a_scheduled_run_that_could_not_start_keeps_its_slot(
    registry: ConnectorRegistry,
) -> None:
    class FlakyJobs(InMemoryJobStore):
        down = False

        async def create_exclusive(self, job: Job) -> Job | None:
            if self.down:
                raise ConnectionError("job store unreachable")
            return await super().create_exclusive(job)

    jobs = FlakyJobs()
    connections = InMemoryConnectionStore()
    conn = await connections.create(await _connection(Schedule.every(hours=24)))
    runner = SyncRunner(registry, job_store=jobs)
    sched = SyncScheduler(runner, connections)
    await sched.schedule(conn, now=T0)
    due = T0 + timedelta(hours=24)
    jobs.down = True

    assert await sched.tick(due + timedelta(seconds=1)) == []
    # Nothing ran, so the slot is still the one that came due, not tomorrow's.
    assert (await sched.next_runs())[conn.id] == due

    jobs.down = False
    started = await sched.tick(due + timedelta(seconds=30))
    assert [job.connection_id for job in started] == [conn.id]
    assert (await sched.next_runs())[conn.id] == due + timedelta(hours=24)
    await _finish(runner, started)


async def test_replicated_takes_the_runners_threshold_for_dead_jobs(
    registry: ConnectorRegistry,
) -> None:
    jobs = InMemoryJobStore()
    connections = InMemoryConnectionStore()
    busy = await connections.create(await _connection(None, "busy"))
    orphaned = await connections.create(await _connection(None, "orphaned"))
    now = datetime.now(UTC)
    sibling = await jobs.create(
        Job(connection_id=busy.id, status=JobStatus.RUNNING, worker_id="sibling", heartbeat_at=now)
    )
    orphan = await jobs.create(
        Job(
            connection_id=orphaned.id,
            status=JobStatus.RUNNING,
            worker_id="gone",
            heartbeat_at=now - timedelta(minutes=5),
        )
    )
    runner = SyncRunner(registry, job_store=jobs, options=SyncOptions(stale_after_seconds=60))
    sched = SyncScheduler(runner, connections, poll_interval_seconds=3600, replicated=True)
    assert sched.stale_after_seconds == 60

    resumed = await sched.start()
    try:
        assert [job.connection_id for job in resumed] == [orphaned.id]
        # A sibling whose heartbeat is fresh keeps its job; only the silent one was dead.
        assert (await jobs.get(sibling.id)).status is JobStatus.RUNNING
        assert (await jobs.get(orphan.id)).status is JobStatus.FAILED
        await _finish(runner, resumed)
    finally:
        await sched.stop()
