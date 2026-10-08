"""In-memory stand-ins for the tables the connector runtime reads and writes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from core.exceptions import LiveSyncJobConflictError


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class FakeConnectionRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get(self, datasource_id):
        row = self.rows.get(datasource_id)
        return dict(row) if row else None

    async def list_all(self):
        return [dict(row) for row in self.rows.values()]

    async def create(self, datasource_id, connector_name, config_id, owner_user_id, catalog, *, update_graph_rag=False):
        now = datetime.now(UTC).isoformat()
        self.rows[datasource_id] = {
            "datasource_id": datasource_id,
            "connector_name": connector_name,
            "config_id": config_id,
            "owner_user_id": owner_user_id,
            "catalog": catalog,
            "update_graph_rag": update_graph_rag,
            "created_at": now,
            "updated_at": now,
        }
        return dict(self.rows[datasource_id])

    async def update(self, datasource_id, **fields):
        row = self.rows.get(datasource_id)
        if row is None:
            return None
        row.update(fields)
        return dict(row)

    async def delete(self, datasource_id):
        return self.rows.pop(datasource_id, None) is not None


class FakeScheduleRepo:
    """Rows shaped like ``ScheduleRepository._to_dict`` (ISO strings for times)."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    @staticmethod
    def to_crontab(cron_expr: str) -> str:
        parts = cron_expr.strip().split()
        return " ".join(p.replace("?", "*") for p in parts[1:]) if len(parts) == 6 else cron_expr

    def add(self, datasource_id, cron_expression, *, enabled=True, timezone="UTC", next_run_at=None):
        now = datetime.now(UTC).isoformat()
        self.rows[datasource_id] = {
            "id": f"schedule-{datasource_id}",
            "datasource_id": datasource_id,
            "cron_expression": cron_expression,
            "preset": "custom",
            "enabled": enabled,
            "update_graph_rag": False,
            "timezone": timezone,
            "next_run_at": _iso(next_run_at),
            "last_run_at": None,
            "last_run_status": None,
            "last_run_error": None,
            "created_at": now,
            "updated_at": now,
        }

    async def get_by_datasource(self, datasource_id):
        row = self.rows.get(datasource_id)
        return dict(row) if row else None

    async def list_all(self):
        return [dict(row) for row in self.rows.values()]

    async def list_due(self, now, limit=100):
        due = [
            dict(row)
            for row in self.rows.values()
            if row["enabled"] and row["next_run_at"] and datetime.fromisoformat(row["next_run_at"]) <= now
        ]
        return sorted(due, key=lambda row: row["next_run_at"])[:limit]

    async def claim_next_run(self, datasource_id, expected, new):
        row = self.rows.get(datasource_id)
        if row is None or row["next_run_at"] != _iso(expected):
            return False
        row["next_run_at"] = _iso(new)
        return True

    async def update_run_times(self, datasource_id, *, next_run_at, last_run_at=None):
        row = self.rows.get(datasource_id)
        if row is None:
            return
        row["next_run_at"] = _iso(next_run_at)
        if last_run_at is not None:
            row["last_run_at"] = _iso(last_run_at)


class FakeJobRepo:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get(self, job_id):
        row = self.rows.get(job_id)
        return dict(row) if row else None

    async def list_recent(self, datasource_id=None, limit=50):
        rows = [r for r in self.rows.values() if datasource_id is None or r["datasource_id"] == datasource_id]
        return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"], reverse=True)[:limit]]

    async def list_active(self, datasource_id=None):
        rows = [
            r
            for r in self.rows.values()
            if r["status"] in ("pending", "running") and (datasource_id is None or r["datasource_id"] == datasource_id)
        ]
        return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"])]

    async def create(self, job_id, datasource_id, **fields):
        self.rows[job_id] = {"id": job_id, "datasource_id": datasource_id, **fields}
        return dict(self.rows[job_id])

    async def create_exclusive(self, job_id, datasource_id, **fields):
        # The partial unique index: one pending or running job per datasource.
        if await self.list_active(datasource_id):
            return None
        return await self.create(job_id, datasource_id, **fields)

    async def update(self, job_id, **fields):
        row = self.rows.get(job_id)
        if row is None:
            return None
        # The same index: a closed job cannot come back to life beside a live one.
        revived = row["status"] not in ("pending", "running") and fields.get("status") in ("pending", "running")
        if revived and await self.list_active(row["datasource_id"]):
            raise LiveSyncJobConflictError(job_id)
        row.update(fields)
        return dict(row)


class FakeStateRepo:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}

    async def get(self, datasource_id):
        return self.states.get(datasource_id)

    async def create(self, datasource_id, state):
        self.states[datasource_id] = state

    async def delete(self, datasource_id):
        return self.states.pop(datasource_id, None) is not None


class FakeDatasourceRepo:
    """Only the collection-metadata part of ``DatasourceRepository``."""

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, Any]] = {}

    def add(self, datasource_id, name="ds", **cmetadata):
        self.collections[datasource_id] = {"uuid": datasource_id, "name": name, "cmetadata": dict(cmetadata)}

    async def get_collection(self, collection_id):
        row = self.collections.get(collection_id)
        return {**row, "cmetadata": dict(row["cmetadata"])} if row else None

    async def update_collection_metadata(self, collection_id, cmetadata):
        if collection_id in self.collections:
            self.collections[collection_id]["cmetadata"] = dict(cmetadata)
        return await self.get_collection(collection_id)


class SyncTables:
    def __init__(self) -> None:
        self.connections = FakeConnectionRepo()
        self.schedules = FakeScheduleRepo()
        self.jobs = FakeJobRepo()
        self.states = FakeStateRepo()
        self.datasources = FakeDatasourceRepo()


@pytest.fixture
def sync_tables(monkeypatch) -> SyncTables:
    """Route every repository accessor of the ingest package to in-memory fakes."""
    tables = SyncTables()
    accessors = {
        "datasource_connection_repository": tables.connections,
        "schedule_repository": tables.schedules,
        "connector_sync_job_repository": tables.jobs,
        "connector_sync_state_repository": tables.states,
        "datasource_repository": tables.datasources,
    }
    for module in (
        "service.ingest.connector_stores",
        "service.ingest.connector_runtime",
        "service.ingest.rag_destination",
        "service.ingest.ingestion_service",
    ):
        for name, repo in accessors.items():
            monkeypatch.setattr(f"{module}.{name}", lambda repo=repo: repo, raising=False)
    return tables
