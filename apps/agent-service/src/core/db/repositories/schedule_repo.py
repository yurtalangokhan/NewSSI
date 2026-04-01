"""Schedule repository — typed CRUD for the ``sync_schedules`` table."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.collection import PgCollection
from core.db.models.schedule import SyncScheduleModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ScheduleRepository(BaseRepository):
    """CRUD operations on the ``sync_schedules`` table.

    Cron helpers (``compute_next_run``, ``_quartz_to_unix``) remain in
    ``service.schedule_db.ScheduleDBManager`` — this repository is
    purely about database access.
    """

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: SyncScheduleModel, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        out: dict[str, Any] = {
            "id": str(row.id),
            "datasource_id": str(row.datasource_id),
            "cron_expression": row.cron_expression,
            "preset": row.preset,
            "enabled": row.enabled,
            "update_graph_rag": row.update_graph_rag,
            "timezone": row.timezone,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "last_run_status": row.last_run_status,
            "last_run_error": row.last_run_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if extra:
            out.update(extra)
        return out

    # ---- read -----------------------------------------------------------

    async def get_by_datasource(self, datasource_id: str) -> dict[str, Any] | None:
        """Return the schedule for a datasource (at most one per constraint)."""
        async with self._session() as session:
            stmt = select(SyncScheduleModel).where(
                SyncScheduleModel.datasource_id == datasource_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_id(self, schedule_id: str) -> dict[str, Any] | None:
        """Return a schedule by its own ID."""
        async with self._session() as session:
            stmt = select(SyncScheduleModel).where(
                SyncScheduleModel.id == schedule_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_all(self) -> list[dict[str, Any]]:
        """Return every schedule, enriched with the datasource name."""
        async with self._session() as session:
            stmt = (
                select(SyncScheduleModel, PgCollection.name.label("datasource_name"))
                .outerjoin(
                    PgCollection,
                    PgCollection.uuid == SyncScheduleModel.datasource_id,
                )
                .order_by(SyncScheduleModel.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.all()

        return [
            self._to_dict(r.SyncScheduleModel, extra={"datasource_name": r.datasource_name})
            for r in rows
        ]

    async def list_enabled(self) -> list[dict[str, Any]]:
        """Return only enabled schedules (used by the scheduler on startup)."""
        async with self._session() as session:
            stmt = (
                select(SyncScheduleModel)
                .where(SyncScheduleModel.enabled.is_(True))
                .order_by(SyncScheduleModel.next_run_at)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    # ---- write ----------------------------------------------------------

    async def create(
        self,
        datasource_id: str,
        cron_expression: str,
        *,
        preset: str = "custom",
        enabled: bool = True,
        update_graph_rag: bool = False,
        tz: str = "UTC",
        next_run_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Insert a new schedule row and return it."""
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                pg_insert(SyncScheduleModel)
                .values(
                    datasource_id=datasource_id,
                    cron_expression=cron_expression,
                    preset=preset,
                    enabled=enabled,
                    update_graph_rag=update_graph_rag,
                    timezone=tz,
                    next_run_at=next_run_at,
                    created_at=now,
                    updated_at=now,
                )
                .returning(SyncScheduleModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def update(
        self,
        datasource_id: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Update fields on the schedule belonging to *datasource_id*.

        Only the allowed field set is accepted; unknown keys are ignored.
        """
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
            return await self.get_by_datasource(datasource_id)

        updates["updated_at"] = datetime.now(UTC)

        async with self._session() as session:
            stmt = (
                update(SyncScheduleModel)
                .where(SyncScheduleModel.datasource_id == datasource_id)
                .values(**updates)
                .returning(SyncScheduleModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def delete(self, datasource_id: str) -> bool:
        """Delete the schedule for a datasource.  Returns ``True`` if removed."""
        async with self._session() as session:
            stmt = delete(SyncScheduleModel).where(
                SyncScheduleModel.datasource_id == datasource_id
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
