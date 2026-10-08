"""Schedule repository — typed CRUD for the ``sync_schedules`` table."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

from croniter import croniter
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.observability.logger import get_logger
from infrastructure.db.models.schedule import SyncScheduleModel
from infrastructure.db.repositories.base import BaseRepository

logger = get_logger(__name__)


class ScheduleRepository(BaseRepository):
    """CRUD operations on the ``sync_schedules`` table, plus the cron math.

    The cron helpers live here because they are the one thing every schedule
    caller needs, and there used to be four copies of them (a facade, the
    service, a route, and the datasource summary) that disagreed: some returned
    a UTC-normalised ISO string, one returned a naive local one.
    """

    # ---- cron helpers ---------------------------------------------------

    @staticmethod
    def _quartz_to_unix(cron_expr: str) -> str:
        """Convert a 6-field Quartz cron to 5-field unix cron for croniter."""
        parts = cron_expr.strip().split()
        if len(parts) == 6:
            return " ".join(p.replace("?", "*") for p in parts[1:])
        return cron_expr

    @staticmethod
    def to_crontab(cron_expr: str) -> str:
        """The five-field crontab form of a stored (Quartz six-field) expression."""
        return ScheduleRepository._quartz_to_unix(cron_expr)

    @staticmethod
    def compute_next_run(cron_expr: str, tz_name: str = "UTC") -> datetime:
        """Return the next fire-time for a Quartz cron expression.

        Raises on an unparseable expression; use :meth:`next_run_iso` where a
        bad value should degrade to ``None`` instead.
        """
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        base = datetime.now(tz)
        cron = croniter(ScheduleRepository._quartz_to_unix(cron_expr), base)
        return cron.get_next(datetime).astimezone(UTC)

    @staticmethod
    def next_run_iso(cron_expr: str, tz_name: str = "UTC") -> str | None:
        """UTC ISO-8601 next fire-time, or ``None`` when it cannot be parsed."""
        try:
            return ScheduleRepository.compute_next_run(cron_expr, tz_name).isoformat()
        except (ValueError, TypeError, KeyError, OverflowError, ZoneInfoNotFoundError):
            return None

    async def mark_run_complete(
        self,
        datasource_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """After a scheduled run finishes, update last_run_* and recompute next_run_at."""
        schedule = await self.get_by_datasource(datasource_id)
        if not schedule:
            return

        next_run = (
            self.compute_next_run(schedule["cron_expression"], schedule.get("timezone", "UTC"))
            if schedule.get("enabled")
            else None
        )

        await self.update(
            datasource_id,
            last_run_at=datetime.now(UTC),
            last_run_status=status,
            last_run_error=error,
            next_run_at=next_run,
        )

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
        async with self._read_session() as session:
            stmt = select(SyncScheduleModel).where(SyncScheduleModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def get_by_id(self, schedule_id: str) -> dict[str, Any] | None:
        """Return a schedule by its own ID."""
        async with self._read_session() as session:
            stmt = select(SyncScheduleModel).where(SyncScheduleModel.id == schedule_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_all(self) -> list[dict[str, Any]]:
        """Return every schedule."""
        async with self._read_session() as session:
            stmt = select(SyncScheduleModel).order_by(SyncScheduleModel.created_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [self._to_dict(r) for r in rows]

    async def list_enabled(self) -> list[dict[str, Any]]:
        """Return only enabled schedules (used by the scheduler on startup)."""
        async with self._read_session() as session:
            stmt = (
                select(SyncScheduleModel)
                .where(SyncScheduleModel.enabled.is_(True))
                .order_by(SyncScheduleModel.next_run_at)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_due(self, now: datetime, limit: int = 100) -> list[dict[str, Any]]:
        """Return enabled schedules whose ``next_run_at`` has passed, most overdue first."""
        async with self._read_session() as session:
            stmt = (
                select(SyncScheduleModel)
                .where(
                    SyncScheduleModel.enabled.is_(True),
                    SyncScheduleModel.next_run_at.isnot(None),
                    SyncScheduleModel.next_run_at <= now,
                )
                .order_by(SyncScheduleModel.next_run_at)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    # ---- write ----------------------------------------------------------

    async def claim_next_run(
        self,
        datasource_id: str,
        expected: datetime | None,
        new: datetime,
    ) -> bool:
        """Move ``next_run_at`` from ``expected`` to ``new`` in one statement.

        ``False`` when the slot had already moved: with several replicas polling
        the same table, only the one whose compare-and-set succeeds starts the run.
        """
        slot_unchanged = (
            SyncScheduleModel.next_run_at.is_(None) if expected is None else SyncScheduleModel.next_run_at == expected
        )
        async with self._session() as session:
            stmt = (
                update(SyncScheduleModel)
                .where(SyncScheduleModel.datasource_id == datasource_id, slot_unchanged)
                .values(next_run_at=new, updated_at=datetime.now(UTC))
            )
            result = await session.execute(stmt)
            return result.rowcount == 1

    async def update_run_times(
        self,
        datasource_id: str,
        *,
        next_run_at: datetime | None,
        last_run_at: datetime | None = None,
    ) -> None:
        """Write the scheduler's bookkeeping; unlike ``update`` it can clear ``next_run_at``."""
        values: dict[str, Any] = {"next_run_at": next_run_at, "updated_at": datetime.now(UTC)}
        if last_run_at is not None:
            values["last_run_at"] = last_run_at
        async with self._session() as session:
            stmt = update(SyncScheduleModel).where(SyncScheduleModel.datasource_id == datasource_id).values(**values)
            await session.execute(stmt)

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
            stmt = delete(SyncScheduleModel).where(SyncScheduleModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            return result.rowcount > 0
