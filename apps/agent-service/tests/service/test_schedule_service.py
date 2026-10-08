"""Sync schedules live in ``sync_schedules`` and are run by the connector scheduler."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from connector import Job, JobStatus
import pytest

from core.exceptions import BadRequestError, ConflictError, NotFoundError
from infrastructure.db.repositories.schedule_repo import ScheduleRepository
from schemas.schedules import SchedulePreset, SyncScheduleInput, SyncScheduleUpdate
from service.runtime import schedule_service as module
from service.runtime.schedule_service import ScheduleService

DS = "44444444-4444-4444-4444-444444444444"


class FakeScheduleRepo:
    """Row storage only; the cron math is the real repository's."""

    compute_next_run = staticmethod(ScheduleRepository.compute_next_run)
    next_run_iso = staticmethod(ScheduleRepository.next_run_iso)

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get_by_datasource(self, datasource_id):
        row = self.rows.get(datasource_id)
        return dict(row) if row else None

    async def list_all(self):
        return [dict(r) for r in self.rows.values()]

    async def create(self, datasource_id, cron_expression, *, preset="custom", enabled=True, update_graph_rag=False, tz="UTC", next_run_at=None):
        self.rows[datasource_id] = {
            "datasource_id": datasource_id,
            "cron_expression": cron_expression,
            "preset": preset,
            "enabled": enabled,
            "timezone": tz,
            "next_run_at": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        return dict(self.rows[datasource_id])

    async def update(self, datasource_id, **fields):
        self.rows[datasource_id].update({k: v for k, v in fields.items() if v is not None})
        return dict(self.rows[datasource_id])

    async def update_run_times(self, datasource_id, *, next_run_at, last_run_at=None):
        self.rows[datasource_id]["next_run_at"] = next_run_at.isoformat() if next_run_at else None

    async def delete(self, datasource_id):
        return self.rows.pop(datasource_id, None) is not None


class FakeConnectionRepo:
    def __init__(self) -> None:
        self.rows = {DS: {"datasource_id": DS, "update_graph_rag": False}}

    async def get(self, datasource_id):
        return self.rows.get(datasource_id)

    async def list_all(self):
        return list(self.rows.values())

    async def update(self, datasource_id, **fields):
        self.rows[datasource_id].update(fields)
        return self.rows[datasource_id]


@pytest.fixture
def env(monkeypatch):
    schedules, connections = FakeScheduleRepo(), FakeConnectionRepo()
    collections = {DS: {"uuid": DS, "name": "ds", "cmetadata": {"sync_status": "syncing", "sync_progress": 10}}}

    async def get_collection(datasource_id):
        return collections.get(datasource_id)

    jobs: list[Job] = []

    async def latest_job(datasource_id):
        return jobs[0] if jobs else None

    async def queue_position(datasource_id):
        return 2

    monkeypatch.setattr(module, "schedule_repository", lambda: schedules)
    monkeypatch.setattr(module, "datasource_connection_repository", lambda: connections)
    monkeypatch.setattr(module, "datasource_repository", lambda: SimpleNamespace(get_collection=get_collection))
    runtime = SimpleNamespace(latest_job=latest_job, queue_position=queue_position)
    return SimpleNamespace(
        service=ScheduleService(runtime=runtime), schedules=schedules, connections=connections, jobs=jobs
    )


@pytest.mark.asyncio
async def test_create_stores_the_definition_and_arms_the_first_run(env):
    created = await env.service.create_schedule(
        DS, SyncScheduleInput(cron_expression="", preset=SchedulePreset.HOURLY, update_graph_rag=True)
    )

    assert created.cron_expression == "0 0 * * * ?" and created.preset == "hourly" and created.enabled
    assert created.update_graph_rag is True and env.connections.rows[DS]["update_graph_rag"] is True
    next_run = datetime.fromisoformat(created.next_run_at)
    assert next_run > datetime.now(UTC) and next_run.minute == 0

    with pytest.raises(ConflictError):
        await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?"))


@pytest.mark.asyncio
async def test_create_rejects_bad_cron_and_unconfigured_datasources(env):
    with pytest.raises(BadRequestError, match="Invalid cron"):
        await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="not a cron"))
    with pytest.raises(BadRequestError, match="Invalid cron"):
        await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?", timezone="Mars/Olympus"))
    with pytest.raises(NotFoundError):
        await env.service.create_schedule("other", SyncScheduleInput(cron_expression="0 0 0 * * ?"))
    assert env.schedules.rows == {}


@pytest.mark.asyncio
async def test_disabling_keeps_the_definition_but_clears_the_next_run(env):
    await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?"))

    disabled = await env.service.update_schedule(DS, SyncScheduleUpdate(enabled=False))

    assert disabled.enabled is False and disabled.next_run_at is None
    assert env.schedules.rows[DS]["cron_expression"] == "0 0 0 * * ?"
    assert env.schedules.rows[DS]["next_run_at"] is None
    with pytest.raises(NotFoundError):
        await env.service.get_schedule(DS)
    assert await env.service.list_all_schedules() == []

    # A disabled definition does not block creating the schedule again.
    recreated = await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 */5 * * * ?"))
    assert recreated.enabled and recreated.cron_expression == "0 */5 * * * ?" and recreated.next_run_at


@pytest.mark.asyncio
async def test_update_changes_the_cron_and_reports_the_last_job(env):
    await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?"))
    finished = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
    env.jobs.append(Job(connection_id=DS, status=JobStatus.FAILED, finished_at=finished))

    updated = await env.service.update_schedule(
        DS, SyncScheduleUpdate(cron_expression="0 30 2 * * ?", timezone="Europe/Istanbul", update_graph_rag=True)
    )

    assert updated.cron_expression == "0 30 2 * * ?" and updated.timezone == "Europe/Istanbul"
    assert updated.update_graph_rag is True
    assert (updated.last_run_at, updated.last_run_status) == ("2026-09-01T03:00:00Z", "failed")
    # 02:30 in Istanbul (UTC+3) is 23:30 UTC.
    assert datetime.fromisoformat(updated.next_run_at).strftime("%H:%M") == "23:30"

    [listed] = await env.service.list_all_schedules()
    assert listed.datasource_id == DS and listed.last_run_status == "failed"


@pytest.mark.asyncio
async def test_a_partial_update_keeps_a_disabled_schedule_disabled(env):
    # PUT with only ``update_graph_rag`` (or only a new cron) used to re-enable the schedule
    # and arm a next run, because a body without ``enabled`` was read as ``enabled: true``.
    await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?"))
    await env.service.update_schedule(DS, SyncScheduleUpdate(enabled=False))

    updated = await env.service.update_schedule(DS, SyncScheduleUpdate(update_graph_rag=True))
    assert updated.enabled is False and updated.next_run_at is None and updated.update_graph_rag is True

    retimed = await env.service.update_schedule(DS, SyncScheduleUpdate(cron_expression="0 30 2 * * ?"))
    assert retimed.enabled is False and retimed.next_run_at is None
    assert retimed.cron_expression == "0 30 2 * * ?", "the new definition is kept for when it is enabled"

    enabled = await env.service.update_schedule(DS, SyncScheduleUpdate(enabled=True))
    assert enabled.enabled is True and enabled.next_run_at and enabled.cron_expression == "0 30 2 * * ?"


@pytest.mark.asyncio
async def test_run_status_and_delete(env):
    await env.service.create_schedule(DS, SyncScheduleInput(cron_expression="0 0 0 * * ?"))

    status = await env.service.get_schedule_run_status(DS)
    assert status.scheduled is True and status.next_run_at and status.queue_position == 2
    assert status.sync_status == "syncing" and status.sync_progress == 10

    assert await env.service.delete_schedule(DS) == {"status": "deleted", "datasource_id": DS}
    assert env.schedules.rows == {}
    assert (await env.service.get_schedule_run_status(DS)).scheduled is False
    with pytest.raises(NotFoundError):
        await env.service.get_schedule_run_status("missing")
