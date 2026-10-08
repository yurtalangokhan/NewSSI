"""State must survive a process restart: SQL stores, crash recovery, resumed syncs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

import sqlalchemy as sa  # noqa: E402

from connector import (  # noqa: E402
    ConfiguredCatalog,
    Connection,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorRegistry,
    Job,
    JobStatus,
    JobTakenOverError,
    JobTrigger,
    Record,
    Schedule,
    ScheduleEntry,
    State,
    SyncAlreadyRunningError,
    SyncMode,
    SyncOptions,
    SyncRunner,
    SyncScheduler,
    SyncState,
)
from connector.destinations.memory import InMemoryDestination  # noqa: E402
from connector.stores_sql import FernetCipher, SqlStores  # noqa: E402
from tests.conftest import FakeSource  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class CrashingSource(FakeSource):
    """Emits two checkpointed rows, then dies on its first run (a pod being killed)."""

    definition = ConnectorDefinition(name="crashy", display_name="C", kind=ConnectorKind.SOURCE)
    crashes_left = 1

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        start = int((state or SyncState()).get("a").get("cursor", 0))
        for i in range(start + 1, start + 3):
            yield Record(stream="a", data={"id": i})
        yield State(stream="a", data={"cursor": start + 2})
        if type(self).crashes_left > 0:
            type(self).crashes_left -= 1
            raise ConnectionResetError("pod killed")
        for i in range(start + 3, start + 5):
            yield Record(stream="a", data={"id": i})
        yield State(stream="a", data={"cursor": start + 4})


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'connector.db').as_posix()}"


def _registry() -> ConnectorRegistry:
    reg = ConnectorRegistry()
    for cls in (FakeSource, CrashingSource, InMemoryDestination):
        reg.register(cls)
    InMemoryDestination.reset()
    return reg


async def _connection(source: str = "fake", schedule: Schedule | None = None) -> Connection:
    src = FakeSource.from_config({"rows": 4})
    return Connection(
        name="orders",
        source_name=source,
        source_config={"rows": 4, "api_key": "super-secret"},
        destination_name="memory",
        destination_config={},
        catalog=ConfiguredCatalog.from_catalog(
            await src.discover(), sync_mode=SyncMode.INCREMENTAL
        ),
        schedule=schedule,
    )


# ---------------------------------------------------------------------------
# stores
# ---------------------------------------------------------------------------


async def test_sql_stores_round_trip_and_encryption_at_rest(db_url: str) -> None:
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    stores = SqlStores(db_url, cipher=FernetCipher(key))
    await stores.create_tables()
    await stores.create_tables()  # idempotent

    conn = await stores.connections.create(await _connection(schedule=Schedule.every(minutes=5)))
    loaded = await stores.connections.get(conn.id)
    assert loaded == conn and loaded.source_config["api_key"] == "super-secret"
    async with stores.engine.connect() as raw:
        payload = (await raw.execute(sa.select(stores.t_connections.c.payload))).scalar_one()
    assert "super-secret" not in payload and "__encrypted__" in payload

    conn.name = "renamed"
    await stores.connections.update(conn)
    assert [c.name for c in await stores.connections.list()] == ["renamed"]

    await stores.states.save(conn.id, SyncState(streams={"a": {"cursor": 4}}))
    assert (await stores.states.load(conn.id)).get("a") == {"cursor": 4}
    assert (await stores.states.load("unknown")).streams == {}

    done = await stores.jobs.create(Job(connection_id=conn.id, status=JobStatus.SUCCEEDED))
    live = await stores.jobs.create(Job(connection_id=conn.id, status=JobStatus.RUNNING))
    assert {j.id for j in await stores.jobs.list(conn.id)} == {done.id, live.id}
    assert [j.id for j in await stores.jobs.list_active(conn.id)] == [live.id]
    assert await stores.jobs.purge(datetime.now(UTC) + timedelta(days=1)) == 1  # finished only
    assert await stores.jobs.get(done.id) is None and await stores.jobs.get(live.id) is not None

    await stores.connections.delete(conn.id)  # cascades to state and schedule
    assert await stores.connections.get(conn.id) is None
    assert (await stores.states.load(conn.id)).streams == {}
    await stores.close()

    wrong_key = SqlStores(db_url)
    await wrong_key.connections.create(await _connection())  # plain rows still work
    await wrong_key.close()


async def test_schedule_claim_is_compare_and_set(db_url: str) -> None:
    stores = SqlStores(db_url)
    await stores.create_tables()
    await stores.schedules.upsert(ScheduleEntry(connection_id="c1", next_run_at=T0))
    assert [e.connection_id for e in await stores.schedules.list_due(T0)] == ["c1"]
    assert await stores.schedules.list_due(T0 - timedelta(seconds=1)) == []

    nxt = T0 + timedelta(minutes=10)
    assert await stores.schedules.claim("c1", T0, nxt) is True
    assert await stores.schedules.claim("c1", T0, nxt) is False  # a second replica loses
    assert (await stores.schedules.get("c1")).next_run_at == nxt
    assert await stores.schedules.claim("missing", T0, nxt) is False
    await stores.close()


async def test_sql_job_store_refuses_to_revive_a_terminal_job(db_url: str) -> None:
    stores = SqlStores(db_url)
    await stores.create_tables()
    job = Job(connection_id="c1", status=JobStatus.RUNNING)
    await stores.jobs.create(job)
    ended = job.model_copy(update={"status": JobStatus.FAILED, "error": "dead"})
    await stores.jobs.update(ended)
    with pytest.raises(JobTakenOverError):
        await stores.jobs.update(job)  # RUNNING over FAILED: the sibling's verdict stands
    assert (await stores.jobs.get(job.id)).status is JobStatus.FAILED
    await stores.jobs.update(ended.model_copy(update={"status": JobStatus.CANCELLED}))
    assert (await stores.jobs.get(job.id)).status is JobStatus.CANCELLED
    fresh = Job(connection_id="c2", status=JobStatus.PENDING)
    await stores.jobs.update(fresh)  # unknown job: inserted, as before
    assert (await stores.jobs.get(fresh.id)).status is JobStatus.PENDING
    await stores.close()


# ---------------------------------------------------------------------------
# restart scenarios
# ---------------------------------------------------------------------------


async def test_crashed_sync_continues_from_the_last_checkpoint(db_url: str) -> None:
    CrashingSource.crashes_left = 1
    stores = SqlStores(db_url)
    await stores.create_tables()
    conn = await stores.connections.create(await _connection("crashy"))
    runner = SyncRunner(_registry(), state_store=stores.states, job_store=stores.jobs)

    first = await runner.run(conn)
    assert first.status is JobStatus.FAILED and "pod killed" in (first.error or "")
    assert (await stores.states.load(conn.id)).get("a") == {"cursor": 2}  # checkpoint survived
    await stores.close()

    # ---- new process: nothing is kept in memory ----
    reopened = SqlStores(db_url)
    runner = SyncRunner(_registry(), state_store=reopened.states, job_store=reopened.jobs)
    second = await runner.run(await reopened.connections.get(conn.id))
    assert second.status is JobStatus.SUCCEEDED
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == [3, 4, 5, 6]  # 1 and 2 not re-read
    assert [j.status for j in await reopened.jobs.list(conn.id)] == [
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
    ]
    await reopened.close()


async def test_restart_recovers_interrupted_job_keeps_schedule_and_resumes(db_url: str) -> None:
    # ---- process 1: one good run, then it is killed in the middle of the next one ----
    stores = SqlStores(db_url)
    await stores.create_tables()
    conn = await stores.connections.create(await _connection(schedule=Schedule.every(minutes=10)))
    runner = SyncRunner(_registry(), state_store=stores.states, job_store=stores.jobs)
    sched = SyncScheduler(runner, stores.connections, stores.schedules)
    await sched.schedule(conn, now=T0)
    assert (await runner.run(conn)).records_read == 4
    orphan = await stores.jobs.create(
        Job(
            connection_id=conn.id,
            status=JobStatus.RUNNING,
            worker_id="dead-pod",
            heartbeat_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await stores.close()

    # ---- process 2 ----
    stores = SqlStores(db_url)
    runner = SyncRunner(_registry(), state_store=stores.states, job_store=stores.jobs)
    sched = SyncScheduler(runner, stores.connections, stores.schedules, poll_interval_seconds=3600)
    resumed = await sched.start()
    try:
        assert (await stores.schedules.get(conn.id)).next_run_at == T0 + timedelta(minutes=10)
        failed = await stores.jobs.get(orphan.id)
        assert failed.status is JobStatus.FAILED and "restart" in (failed.error or "")
        assert [j.trigger for j in resumed] == [JobTrigger.RESUME]
        done = await runner.wait(resumed[0].id)
        assert done.status is JobStatus.SUCCEEDED and done.worker_id == runner.worker_id
        assert [r["id"] for r in InMemoryDestination.sink["a"]] == [5, 6, 7, 8]
    finally:
        await sched.stop()
        await stores.close()


async def test_live_sibling_job_is_not_recovered_and_blocks_a_second_run(db_url: str) -> None:
    stores = SqlStores(db_url)
    await stores.create_tables()
    conn = await stores.connections.create(await _connection())
    sibling = await stores.jobs.create(
        Job(
            connection_id=conn.id,
            status=JobStatus.RUNNING,
            worker_id="pod-b",
            heartbeat_at=datetime.now(UTC),
        )
    )
    runner = SyncRunner(
        _registry(),
        state_store=stores.states,
        job_store=stores.jobs,
        options=SyncOptions(stale_after_seconds=300),
    )
    assert await runner.recover_interrupted(stale_after_seconds=300) == []
    assert (await stores.jobs.get(sibling.id)).status is JobStatus.RUNNING
    assert await runner.has_active_job(conn.id)
    with pytest.raises(SyncAlreadyRunningError, match="on worker 'pod-b'"):
        await runner.run(conn)

    # once the sibling's heartbeat goes stale it is treated as dead
    sibling.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
    await stores.jobs.update(sibling)
    assert [j.id for j in await runner.recover_interrupted(stale_after_seconds=300)] == [sibling.id]
    assert (await runner.run(conn)).status is JobStatus.SUCCEEDED
    await stores.close()


async def test_heartbeat_keeps_a_quiet_job_alive(db_url: str) -> None:
    import asyncio

    class QuietSource(FakeSource):
        definition = ConnectorDefinition(name="quiet", display_name="Q", kind=ConnectorKind.SOURCE)

        async def read(
            self, catalog: ConfiguredCatalog, state: SyncState | None = None
        ) -> AsyncIterator[Record | State]:
            await asyncio.sleep(0.15)  # a slow query: no batches, so no progress updates
            yield Record(stream="a", data={"id": 1})

    stores = SqlStores(db_url)
    await stores.create_tables()
    reg = _registry()
    reg.register(QuietSource)
    conn = await stores.connections.create(await _connection("quiet"))
    runner = SyncRunner(
        reg,
        state_store=stores.states,
        job_store=stores.jobs,
        options=SyncOptions(heartbeat_interval_seconds=0.03),
    )
    job = await runner.start(conn)
    first_beat = job.heartbeat_at  # the runner mutates `job` in place
    await asyncio.sleep(0.1)
    beating = await stores.jobs.get(job.id)
    assert beating.status is JobStatus.RUNNING
    assert beating.heartbeat_at > first_beat
    assert (await runner.wait(job.id)).status is JobStatus.SUCCEEDED
    await stores.close()


async def test_sql_job_store_creates_one_live_job_per_connection(db_url: str) -> None:
    stores = SqlStores(db_url)
    await stores.create_tables()
    first = await stores.jobs.create_exclusive(Job(connection_id="c", worker_id="a"))
    assert first is not None
    assert await stores.jobs.create_exclusive(Job(connection_id="c", worker_id="b")) is None
    assert await stores.jobs.create_exclusive(Job(connection_id="other")) is not None
    assert [j.worker_id for j in await stores.jobs.list_active("c")] == ["a"]

    first.status = JobStatus.FAILED
    await stores.jobs.update(first)
    again = await stores.jobs.create_exclusive(Job(connection_id="c", worker_id="b"))
    assert again is not None and again.heartbeat_at is None
    assert [j.worker_id for j in await stores.jobs.list_active("c")] == ["b"]
    await stores.close()


async def test_create_exclusive_tells_a_lost_race_from_any_other_integrity_error(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    stores = SqlStores(db_url)
    await stores.create_tables()

    # The same primary key again, and no live job in sight: a defect the caller must
    # hear about, not "the connection is already being synced".
    done = await stores.jobs.create(Job(connection_id="c", status=JobStatus.SUCCEEDED))
    with pytest.raises(sa.exc.IntegrityError):
        await stores.jobs.create_exclusive(Job(id=done.id, connection_id="c"))

    class LostRace:
        """Inserts are refused the way a host's unique index refuses the loser of a race."""

        def __init__(self, engine: object) -> None:
            self._engine = engine

        def connect(self) -> object:
            return self._engine.connect()

        def begin(self) -> object:
            raise sa.exc.IntegrityError("INSERT INTO connector_jobs", {}, Exception("unique"))

    await stores.jobs.create(Job(connection_id="busy", worker_id="sibling"))
    real = stores.engine
    monkeypatch.setattr(stores, "engine", LostRace(real))
    # The sibling's job is there by the time the insert is refused: not created, no error.
    assert await stores.jobs.create_exclusive(Job(connection_id="busy", worker_id="me")) is None
    # Refused although nothing is live on the connection: something else is wrong.
    with pytest.raises(sa.exc.IntegrityError):
        await stores.jobs.create_exclusive(Job(connection_id="quiet", worker_id="me"))
    monkeypatch.setattr(stores, "engine", real)
    await stores.close()
