"""
Sync Schedule Database Manager.

Manages the ``sync_schedules`` table – creation, CRUD operations,
and next-run-time computation via *croniter*.

Single Responsibility: only talks to the database.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from croniter import croniter
from psycopg.rows import dict_row

from service.store import get_store

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# SQL – table creation
# ------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sync_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    datasource_id   UUID NOT NULL,
    cron_expression TEXT NOT NULL,
    preset          TEXT NOT NULL DEFAULT 'custom',
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    update_graph_rag BOOLEAN NOT NULL DEFAULT FALSE,
    timezone        TEXT NOT NULL DEFAULT 'UTC',
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    last_run_status TEXT,
    last_run_error  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_datasource
        FOREIGN KEY (datasource_id)
        REFERENCES langchain_pg_collection(uuid)
        ON DELETE CASCADE,
    CONSTRAINT uq_datasource_schedule
        UNIQUE (datasource_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_schedules_enabled
    ON sync_schedules (enabled) WHERE enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_sync_schedules_next_run
    ON sync_schedules (next_run_at) WHERE enabled = TRUE;
"""


# ------------------------------------------------------------------
# Manager class
# ------------------------------------------------------------------


class ScheduleDBManager:
    """Encapsulates all sync_schedules DB operations."""

    # ---- bootstrap -------------------------------------------------------

    @staticmethod
    async def ensure_table() -> None:
        """Create the sync_schedules table if it does not exist."""
        store = get_store()
        if not store or not store.pool:
            logger.warning("Store not ready – skipping sync_schedules table creation")
            return
        async with store.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(CREATE_TABLE_SQL)
        logger.info("sync_schedules table ensured")

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def compute_next_run(cron_expr: str, tz_name: str = "UTC") -> datetime:
        """Return the next fire-time for a cron expression."""
        import zoneinfo

        tz = zoneinfo.ZoneInfo(tz_name)
        base = datetime.now(tz)
        cron = croniter(cron_expr, base)
        return cron.get_next(datetime).astimezone(timezone.utc)

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        """Normalise a DB row to a JSON-friendly dict."""
        out: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        # Ensure UUID fields are strings
        for f in ("id", "datasource_id"):
            if f in out and out[f] is not None:
                out[f] = str(out[f])
        return out

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
        store = get_store()
        schedule_id = uuid4()
        next_run = ScheduleDBManager.compute_next_run(cron_expression, tz) if enabled else None
        now = datetime.now(timezone.utc)

        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO sync_schedules
                        (id, datasource_id, cron_expression, preset, enabled,
                         update_graph_rag, timezone, next_run_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        schedule_id,
                        datasource_id,
                        cron_expression,
                        preset,
                        enabled,
                        update_graph_rag,
                        tz,
                        next_run,
                        now,
                        now,
                    ),
                )
                row = await cur.fetchone()
                return ScheduleDBManager._row_to_dict(row)

    @staticmethod
    async def get_by_datasource(datasource_id: str) -> Optional[dict[str, Any]]:
        """Return the schedule for a datasource (at most one per constraint)."""
        store = get_store()
        if not store or not store.pool:
            return None
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM sync_schedules WHERE datasource_id = %s",
                    (datasource_id,),
                )
                row = await cur.fetchone()
                return ScheduleDBManager._row_to_dict(row) if row else None

    @staticmethod
    async def get_by_id(schedule_id: str) -> Optional[dict[str, Any]]:
        """Return a schedule by its own ID."""
        store = get_store()
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM sync_schedules WHERE id = %s",
                    (schedule_id,),
                )
                row = await cur.fetchone()
                return ScheduleDBManager._row_to_dict(row) if row else None

    @staticmethod
    async def list_all() -> list[dict[str, Any]]:
        """Return every schedule (for admin/list endpoint)."""
        store = get_store()
        if not store or not store.pool:
            return []
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT s.*, c.name AS datasource_name
                    FROM sync_schedules s
                    LEFT JOIN langchain_pg_collection c ON c.uuid = s.datasource_id
                    ORDER BY s.created_at DESC
                    """
                )
                rows = await cur.fetchall()
                return [ScheduleDBManager._row_to_dict(r) for r in rows]

    @staticmethod
    async def list_enabled() -> list[dict[str, Any]]:
        """Return only enabled schedules (used by the scheduler on startup)."""
        store = get_store()
        if not store or not store.pool:
            return []
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM sync_schedules WHERE enabled = TRUE ORDER BY next_run_at"
                )
                rows = await cur.fetchall()
                return [ScheduleDBManager._row_to_dict(r) for r in rows]

    @staticmethod
    async def update(
        datasource_id: str,
        **fields: Any,
    ) -> Optional[dict[str, Any]]:
        """Update fields on the schedule belonging to *datasource_id*."""
        store = get_store()
        allowed = {
            "cron_expression",
            "preset",
            "enabled",
            "update_graph_rag",
            "timezone",
            "next_run_at",
            "last_run_at",
            "last_run_status",
            "last_run_error",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return await ScheduleDBManager.get_by_datasource(datasource_id)

        updates["updated_at"] = datetime.now(timezone.utc)
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [datasource_id]

        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"UPDATE sync_schedules SET {set_clause} WHERE datasource_id = %s RETURNING *",
                    values,
                )
                row = await cur.fetchone()
                return ScheduleDBManager._row_to_dict(row) if row else None

    @staticmethod
    async def delete(datasource_id: str) -> bool:
        """Delete the schedule for a datasource. Returns True if a row was removed."""
        store = get_store()
        async with store.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM sync_schedules WHERE datasource_id = %s",
                    (datasource_id,),
                )
                return cur.rowcount > 0

    @staticmethod
    async def mark_run_complete(
        datasource_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """After a scheduled run finishes, update last_run_* and recompute next_run_at."""
        schedule = await ScheduleDBManager.get_by_datasource(datasource_id)
        if not schedule:
            return

        now = datetime.now(timezone.utc)
        next_run = (
            ScheduleDBManager.compute_next_run(
                schedule["cron_expression"], schedule.get("timezone", "UTC")
            )
            if schedule.get("enabled")
            else None
        )

        await ScheduleDBManager.update(
            datasource_id,
            last_run_at=now,
            last_run_status=status,
            last_run_error=error,
            next_run_at=next_run,
        )
