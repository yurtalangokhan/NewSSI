"""connector-py store protocols over agent-service repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from connector import (
    ConfiguredCatalog,
    ConfiguredStream,
    ConnectionReader,
    ConnectionStore,
    ExclusiveJobStore,
    Job,
    JobStatus,
    JobTakenOverError,
    JobTrigger,
    ScheduleStore,
    StateStore,
    Stream,
    StreamStats,
    SyncState,
)
import pytest

from service.ingest.connector_stores import (
    RAG_DESTINATION,
    DatasourceConnectionStore,
    SyncJobStore,
    SyncScheduleStore,
    SyncStateStore,
)

DS = "11111111-1111-1111-1111-111111111111"
CATALOG = ConfiguredCatalog(streams=[ConfiguredStream(stream=Stream(name="orders"))]).model_dump(mode="json")
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_the_adapters_satisfy_the_package_protocols():
    assert isinstance(DatasourceConnectionStore(), ConnectionReader)
    # The runtime only reads connections; DatasourceService writes them through the repository.
    assert not isinstance(DatasourceConnectionStore(), ConnectionStore)
    assert isinstance(SyncJobStore(), ExclusiveJobStore)
    assert isinstance(SyncStateStore(), StateStore)
    assert isinstance(SyncScheduleStore(), ScheduleStore)


@pytest.mark.asyncio
async def test_get_carries_a_pointer_to_the_config_and_the_schedule(sync_tables):
    await sync_tables.connections.create(DS, "postgres", "cfg-1", "owner-1", CATALOG, update_graph_rag=True)
    sync_tables.schedules.add(DS, "0 0 3 * * ?", timezone="Europe/Istanbul")

    connection = await DatasourceConnectionStore().get(DS)

    assert connection.id == DS and connection.source_name == "postgres"
    # No credential travels with a connection: the factory fetches it when a sync runs.
    assert connection.source_config == {}
    assert connection.metadata["config_id"] == "cfg-1" and connection.metadata["owner_user_id"] == "owner-1"
    assert connection.destination_name == RAG_DESTINATION
    assert connection.destination_config == {"datasource_id": DS, "connector_type": "postgres"}
    assert connection.catalog.names() == ["orders"]
    # Quartz six-field input is stored; the scheduler gets the crontab form.
    assert connection.schedule.cron_expression == "0 3 * * *"
    assert connection.schedule.timezone == "Europe/Istanbul"
    assert connection.metadata["update_graph_rag"] is True
    assert await DatasourceConnectionStore().get("unknown") is None


@pytest.mark.asyncio
async def test_list_carries_schedules(sync_tables):
    await sync_tables.connections.create(DS, "postgres", "cfg-1", "owner-1", CATALOG)
    sync_tables.schedules.add(DS, "0 */5 * * * ?", enabled=False)

    [connection] = await DatasourceConnectionStore().list()

    assert connection.source_config == {}
    assert connection.schedule.enabled is False


@pytest.mark.asyncio
async def test_job_store_admits_one_live_job_per_datasource(sync_tables):
    store = SyncJobStore()
    first = Job(connection_id=DS, worker_id="pod-a", heartbeat_at=T0)

    assert await store.create_exclusive(first) is first
    assert await store.create_exclusive(Job(connection_id=DS, worker_id="pod-b")) is None
    assert [job.worker_id for job in await store.list_active(DS)] == ["pod-a"]

    first.status = JobStatus.FAILED
    await store.update(first)
    assert await store.create_exclusive(Job(connection_id=DS, worker_id="pod-b")) is not None


@pytest.mark.asyncio
async def test_a_job_that_was_replaced_says_so_when_its_worker_writes_it_again(sync_tables):
    store = SyncJobStore()
    first = Job(connection_id=DS, worker_id="pod-a", status=JobStatus.RUNNING, heartbeat_at=T0)
    await store.create_exclusive(first)
    # pod-a went silent: a sibling declared its job dead and started the datasource again.
    await sync_tables.jobs.update(first.id, status="failed", error="interrupted")
    assert await store.create_exclusive(Job(connection_id=DS, worker_id="pod-b")) is not None

    # pod-a comes back and reports progress. The database refuses a second live job;
    # the runner is told in its own terms (``JobTakenOverError`` ends the run), not with
    # the statement that failed.
    with pytest.raises(JobTakenOverError, match="ended by another worker") as refused:
        await store.update(first)

    assert "connector_sync_jobs" not in str(refused.value)
    assert sync_tables.jobs.rows[first.id]["status"] == "failed"


@pytest.mark.asyncio
async def test_job_store_round_trip(sync_tables):
    store = SyncJobStore()
    job = Job(connection_id=DS, trigger=JobTrigger.SCHEDULE, worker_id="w1", heartbeat_at=T0)
    await store.create(job)
    assert [j.id for j in await store.list_active(DS)] == [job.id]

    job.status = JobStatus.SUCCEEDED
    job.started_at, job.finished_at = T0, T0 + timedelta(seconds=9)
    job.stats["orders"] = StreamStats(records_read=3, records_written=3, batches=2)
    await store.update(job)

    loaded = await store.get(job.id)
    assert loaded.status is JobStatus.SUCCEEDED and loaded.trigger is JobTrigger.SCHEDULE
    assert loaded.records_written == 3 and loaded.finished_at == T0 + timedelta(seconds=9)
    assert await store.list_active() == []
    assert [j.id for j in await store.list(DS)] == [job.id]
    assert await store.get("missing") is None


@pytest.mark.asyncio
async def test_state_store_round_trip(sync_tables):
    store = SyncStateStore()
    assert (await store.load(DS)).streams == {}

    await store.save(DS, SyncState(streams={"orders": {"cursor": 7}}))
    assert (await store.load(DS)).get("orders") == {"cursor": 7}

    # A full refresh forgets the checkpoints: the row goes, not just its content.
    await store.reset(DS)
    assert (await store.load(DS)).streams == {}
    assert DS not in sync_tables.states.states


@pytest.mark.asyncio
async def test_schedule_store_keeps_the_definition_when_the_entry_is_deleted(sync_tables):
    sync_tables.schedules.add(DS, "0 0 * * * ?", next_run_at=T0)
    store = SyncScheduleStore()

    entry = await store.get(DS)
    assert entry.next_run_at == T0 and entry.enabled is True
    assert [e.connection_id for e in await store.list()] == [DS]
    assert [e.connection_id for e in await store.list_due(T0 + timedelta(minutes=1))] == [DS]

    await store.delete(DS)

    assert DS in sync_tables.schedules.rows, "the schedule definition belongs to the schedule API"
    assert await store.get(DS) is None
    assert await store.list() == [] and await store.list_due(T0 + timedelta(days=1)) == []


@pytest.mark.asyncio
async def test_schedule_store_claim_is_compare_and_set(sync_tables):
    sync_tables.schedules.add(DS, "0 0 * * * ?", next_run_at=T0)
    store = SyncScheduleStore()
    upcoming = T0 + timedelta(hours=1)

    assert await store.claim(DS, T0, upcoming) is True
    assert await store.claim(DS, T0, upcoming) is False, "a second replica must lose the slot"
    assert (await store.get(DS)).next_run_at == upcoming

    entry = await store.get(DS)
    entry.last_run_at = T0
    await store.upsert(entry)
    assert (await store.get(DS)).last_run_at == T0
