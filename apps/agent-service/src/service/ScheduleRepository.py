"""
Sync Schedule Database Manager.

Manages the ``sync_schedules`` table – creation, CRUD operations,
and next-run-time computation via *croniter*.

All database access is now delegated to
:class:`~core.db.repositories.ScheduleRepository`.  This module keeps
the ``ScheduleDBManager`` façade (same static-method signatures) so
that existing callers continue to work unchanged.
"""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)
import logging as _stdlib_logging
logger_stdlib = _stdlib_logging.getLogger(__name__)
from datetime import UTC, datetime
from typing import Any

from croniter import croniter

from core.db import ScheduleRepository

logger = get_logger(__name__)


def _repo() -> ScheduleRepository:
    return ScheduleRepository()


class ScheduleDBManager:
    """Encapsulates all sync_schedules DB operations."""

    # ---- bootstrap -------------------------------------------------------

    @staticmethod
    async def ensure_table() -> None:
        """No-op — table creation is managed by Alembic migrations."""
        logger.info("sync_schedules table managed by Alembic – skipping ensure_table")

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _quartz_to_unix(cron_expr: str) -> str:
        """Convert 6-field Quartz cron to 5-field unix cron for croniter."""
        parts = cron_expr.strip().split()
        if len(parts) == 6:
            return " ".join(p.replace("?", "*") for p in parts[1:])
        return cron_expr

    @staticmethod
    def compute_next_run(cron_expr: str, tz_name: str = "UTC") -> datetime:
        """Return the next fire-time for a Quartz cron expression."""
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        base = datetime.now(tz)
        unix_cron = ScheduleDBManager._quartz_to_unix(cron_expr)
        cron = croniter(unix_cron, base)
        return cron.get_next(datetime).astimezone(UTC)

    # ---- CRUD ------------------------------------------------------------

    @staticmethod
    async def create(
        datasource_id: str,
        cron_expression: str,
        preset: str = "custom",
        enabled: bool = True,
        update_graph_rag: bool = False,
        tz: str = "UTC",
    ) -> dict[str, Any]:
        """Insert a new schedule row and return it."""
        next_run = ScheduleDBManager.compute_next_run(cron_expression, tz) if enabled else None
        return await _repo().create(
            datasource_id=datasource_id,
            cron_expression=cron_expression,
            preset=preset,
            enabled=enabled,
            update_graph_rag=update_graph_rag,
            tz=tz,
            next_run_at=next_run,
        )

    @staticmethod
    async def get_by_datasource(datasource_id: str) -> dict[str, Any] | None:
        """Return the schedule for a datasource (at most one per constraint)."""
        return await _repo().get_by_datasource(datasource_id)

    @staticmethod
    async def get_by_id(schedule_id: str) -> dict[str, Any] | None:
        """Return a schedule by its own ID."""
        return await _repo().get_by_id(schedule_id)

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return every schedule (for admin/list endpoint)."""
        return await _repo().list_all()

    @staticmethod
    async def list_enabled() -> list[dict[str, Any]]:
        """Return only enabled schedules (used by the scheduler on startup)."""
        return await _repo().list_enabled()

    @staticmethod
    async def update(
        datasource_id: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Update fields on the schedule belonging to *datasource_id*."""
        return await _repo().update(datasource_id, **fields)

    @staticmethod
    async def delete(datasource_id: str) -> bool:
        """Delete the schedule for a datasource. Returns True if a row was removed."""
        return await _repo().delete(datasource_id)

    @staticmethod
    async def mark_run_complete(
        datasource_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """After a scheduled run finishes, update last_run_* and recompute next_run_at."""
        schedule = await _repo().get_by_datasource(datasource_id)
        if not schedule:
            return

        now = datetime.now(UTC)
        next_run = (
            ScheduleDBManager.compute_next_run(
                schedule["cron_expression"], schedule.get("timezone", "UTC")
            )
            if schedule.get("enabled")
            else None
        )

        await _repo().update(
            datasource_id,
            last_run_at=now,
            last_run_status=status,
            last_run_error=error,
            next_run_at=next_run,
        )
