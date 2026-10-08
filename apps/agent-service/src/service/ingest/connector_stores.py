"""connector-py store protocols, implemented over agent-service repositories.

The sync runner and scheduler in ``packages/connector-py`` only know four small
protocols (connections, jobs, state, schedules). These adapters satisfy them
with the service's own tables, so the package never opens a database connection
and every query keeps its single home in ``infrastructure.db.repositories``.

Connector configurations are not in this database, and not in the
``Connection`` objects built here either. A connection carries a pointer
(``metadata["config_id"]`` / ``["owner_user_id"]``) to the encrypted
configuration user-service keeps for its owner; the runtime's connector factory
follows it at the moment a sync starts running.
"""

from __future__ import annotations

import builtins
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from connector import (
    ConfiguredCatalog,
    Connection,
    Job,
    JobStatus,
    JobTakenOverError,
    JobTrigger,
    Schedule,
    ScheduleEntry,
    StreamStats,
    SyncState,
)

from core.exceptions import LiveSyncJobConflictError
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import (
    connector_sync_job_repository,
    connector_sync_state_repository,
    datasource_connection_repository,
    schedule_repository,
)
from integrations import user_service_client

logger = get_logger(__name__)

#: Name of the in-process destination that streams batches to rag-service.
RAG_DESTINATION = "rag_datasource"

#: ``(owner_user_id, config_id) -> decrypted configuration`` or ``None``.
ConfigReader = Callable[[str, str], Awaitable[dict[str, Any] | None]]
#: ``(owner_user_id, config_id) -> does the stored configuration still exist``.
ConfigExists = Callable[[str, str], Awaitable[bool]]


async def read_stored_config(owner_user_id: str, config_id: str) -> dict[str, Any] | None:
    """Decrypted configuration from user-service, or ``None`` when the row is gone."""
    stored = await user_service_client.get_connector_config(owner_user_id, config_id)
    if stored is None:
        return None
    config = stored.get("config")
    return config if isinstance(config, dict) else None


async def stored_config_exists(owner_user_id: str, config_id: str) -> bool:
    """Is the configuration still stored? Answered from the owner's configuration list,
    which carries metadata only: no credentials leave user-service for a check."""
    configs = await user_service_client.list_connector_configs(owner_user_id)
    return any(str(item.get("id")) == str(config_id) for item in configs)


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def schedule_from_row(row: dict[str, Any] | None) -> Schedule | None:
    """The connector-py schedule of a ``sync_schedules`` row."""
    if not row or not row.get("cron_expression"):
        return None
    return Schedule.cron(
        schedule_repository().to_crontab(row["cron_expression"]),
        row.get("timezone") or "UTC",
        enabled=bool(row.get("enabled", True)),
    )


def connection_from_row(row: dict[str, Any], schedule_row: dict[str, Any] | None) -> Connection:
    """Build the connector-py ``Connection`` of a ``datasource_connections`` row.

    ``source_config`` stays empty on purpose: no credential travels with a
    connection. ``metadata`` says where the configuration is stored.
    """
    datasource_id = row["datasource_id"]
    connection = Connection(
        id=datasource_id,
        name=datasource_id,
        source_name=row["connector_name"],
        source_config={},
        destination_name=RAG_DESTINATION,
        destination_config={
            "datasource_id": datasource_id,
            "connector_type": row["connector_name"],
        },
        catalog=ConfiguredCatalog.model_validate(row.get("catalog") or {}),
        schedule=schedule_from_row(schedule_row),
        metadata={
            "config_id": row["config_id"],
            "owner_user_id": row["owner_user_id"],
            "update_graph_rag": bool(row.get("update_graph_rag", False)),
        },
    )
    if row.get("created_at"):
        connection.created_at = datetime.fromisoformat(row["created_at"])
    return connection


class DatasourceConnectionStore:
    """``ConnectionReader`` over ``datasource_connections`` + ``sync_schedules``.

    A connection's id is its datasource id. The runtime only reads connections;
    creating, changing and deleting them is ``DatasourceService``'s job, through
    the repository.
    """

    async def get(self, connection_id: str) -> Connection | None:
        row = await datasource_connection_repository().get(connection_id)
        if row is None:
            return None
        schedule_row = await schedule_repository().get_by_datasource(connection_id)
        return connection_from_row(row, schedule_row)

    async def list(self) -> list[Connection]:
        rows = await datasource_connection_repository().list_all()
        if not rows:
            return []
        schedules = {s["datasource_id"]: s for s in await schedule_repository().list_all()}
        return [connection_from_row(r, schedules.get(r["datasource_id"])) for r in rows]


def _job_from_row(row: dict[str, Any]) -> Job:
    return Job(
        id=row["id"],
        connection_id=row["datasource_id"],
        status=JobStatus(row["status"]),
        trigger=JobTrigger(row["trigger"]),
        stats={name: StreamStats(**values) for name, values in (row.get("stats") or {}).items()},
        error=row.get("error"),
        worker_id=row.get("worker_id"),
        heartbeat_at=row.get("heartbeat_at"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
    )


def _job_fields(job: Job) -> dict[str, Any]:
    return {
        "status": job.status.value,
        "stats": {name: stats.model_dump() for name, stats in job.stats.items()},
        "error": job.error,
        "worker_id": job.worker_id,
        "heartbeat_at": job.heartbeat_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


class SyncJobStore:
    """``ExclusiveJobStore`` over ``connector_sync_jobs``."""

    async def create(self, job: Job) -> Job:
        await connector_sync_job_repository().create(
            job.id,
            job.connection_id,
            trigger=job.trigger.value,
            created_at=job.created_at,
            **_job_fields(job),
        )
        return job

    async def create_exclusive(self, job: Job) -> Job | None:
        """Create ``job`` unless its datasource already has a live one (decided by the database)."""
        row = await connector_sync_job_repository().create_exclusive(
            job.id,
            job.connection_id,
            trigger=job.trigger.value,
            created_at=job.created_at,
            **_job_fields(job),
        )
        return job if row is not None else None

    async def update(self, job: Job) -> Job:
        try:
            await connector_sync_job_repository().update(job.id, **_job_fields(job))
        except LiveSyncJobConflictError as exc:
            # This worker went silent long enough for a sibling to declare the job
            # dead (and maybe start the datasource again). The runner ends the run
            # on this error instead of writing RUNNING back over the sibling's verdict.
            raise JobTakenOverError(job.id) from exc
        return job

    async def get(self, job_id: str) -> Job | None:
        row = await connector_sync_job_repository().get(job_id)
        return _job_from_row(row) if row else None

    async def list(self, connection_id: str | None = None, limit: int = 50) -> list[Job]:
        rows = await connector_sync_job_repository().list_recent(connection_id, limit)
        return [_job_from_row(r) for r in rows]

    # ``builtins.list``: the ``list`` method above shadows the type in this class body.
    async def list_active(self, connection_id: str | None = None) -> builtins.list[Job]:
        rows = await connector_sync_job_repository().list_active(connection_id)
        return [_job_from_row(r) for r in rows]


class SyncStateStore:
    """``StateStore`` over ``connector_sync_state`` (incremental checkpoints)."""

    async def load(self, connection_id: str) -> SyncState:
        stored = await connector_sync_state_repository().get(connection_id)
        return SyncState(streams=stored or {})

    async def save(self, connection_id: str, state: SyncState) -> None:
        await connector_sync_state_repository().create(connection_id, state.streams)

    async def reset(self, connection_id: str) -> None:
        await connector_sync_state_repository().delete(connection_id)


def _entry_from_row(row: dict[str, Any]) -> ScheduleEntry:
    schedule = schedule_from_row(row)
    entry = ScheduleEntry(
        connection_id=row["datasource_id"],
        next_run_at=_parse_time(row.get("next_run_at")),
        last_run_at=_parse_time(row.get("last_run_at")),
        enabled=bool(row.get("enabled", True)),
        # The row is both the schedule definition and its bookkeeping, so the
        # fingerprint of what is stored always equals the definition's.
        fingerprint=schedule.fingerprint() if schedule else "",
    )
    if row.get("updated_at"):
        entry.updated_at = datetime.fromisoformat(row["updated_at"])
    return entry


class SyncScheduleStore:
    """``ScheduleStore`` over ``sync_schedules``.

    The table's rows are schedule *definitions* that the schedule API owns; the
    scheduler only keeps ``next_run_at``/``last_run_at`` on them. "No entry"
    therefore means "``next_run_at`` is NULL": ``delete`` clears the slot and
    never removes a definition, and ``upsert`` cannot create one.
    """

    async def get(self, connection_id: str) -> ScheduleEntry | None:
        row = await schedule_repository().get_by_datasource(connection_id)
        if row is None or not row.get("next_run_at"):
            return None
        return _entry_from_row(row)

    async def upsert(self, entry: ScheduleEntry) -> ScheduleEntry:
        await schedule_repository().update_run_times(
            entry.connection_id,
            next_run_at=entry.next_run_at,
            last_run_at=entry.last_run_at,
        )
        return entry

    async def delete(self, connection_id: str) -> None:
        await schedule_repository().update_run_times(connection_id, next_run_at=None)

    async def list(self) -> list[ScheduleEntry]:
        rows = await schedule_repository().list_all()
        return [_entry_from_row(r) for r in rows if r.get("next_run_at")]

    # ``builtins.list``: the ``list`` method above shadows the type in this class body.
    async def list_due(self, now: datetime, limit: int = 100) -> builtins.list[ScheduleEntry]:
        rows = await schedule_repository().list_due(now, limit)
        return [_entry_from_row(r) for r in rows]

    async def claim(
        self,
        connection_id: str,
        expected_next_run_at: datetime | None,
        new_next_run_at: datetime,
    ) -> bool:
        return await schedule_repository().claim_next_run(connection_id, expected_next_run_at, new_next_run_at)
