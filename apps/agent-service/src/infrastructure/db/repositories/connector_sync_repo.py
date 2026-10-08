"""Connector sync repositories — jobs and incremental state of datasource syncs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from core.exceptions import LiveSyncJobConflictError
from infrastructure.db.models.connector_sync import (
    ACTIVE_JOB_INDEX,
    ACTIVE_JOB_PREDICATE,
    ACTIVE_STATUSES,
    ConnectorSyncJobModel,
    ConnectorSyncStateModel,
)
from infrastructure.db.repositories.base import BaseRepository


class ConnectorSyncJobRepository(BaseRepository):
    """CRUD operations on the ``connector_sync_jobs`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: ConnectorSyncJobModel) -> dict[str, Any]:
        """Convert an ORM row to a dict; timestamps stay ``datetime``."""
        return {
            "id": str(row.id),
            "datasource_id": str(row.datasource_id),
            "status": row.status,
            "trigger": row.trigger,
            "stats": row.stats or {},
            "error": row.error,
            "worker_id": row.worker_id,
            "heartbeat_at": row.heartbeat_at,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }

    # ---- read -----------------------------------------------------------

    async def get(self, job_id: str) -> dict[str, Any] | None:
        """Return one job by id."""
        async with self._read_session() as session:
            stmt = select(ConnectorSyncJobModel).where(ConnectorSyncJobModel.id == job_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_recent(self, datasource_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return the newest jobs, optionally of one datasource."""
        async with self._read_session() as session:
            stmt = select(ConnectorSyncJobModel).order_by(ConnectorSyncJobModel.created_at.desc()).limit(limit)
            if datasource_id is not None:
                stmt = stmt.where(ConnectorSyncJobModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_active(self, datasource_id: str | None = None) -> list[dict[str, Any]]:
        """Return pending and running jobs, oldest first, optionally of one datasource."""
        async with self._read_session() as session:
            stmt = (
                select(ConnectorSyncJobModel)
                .where(ConnectorSyncJobModel.status.in_(ACTIVE_STATUSES))
                .order_by(ConnectorSyncJobModel.created_at)
            )
            if datasource_id is not None:
                stmt = stmt.where(ConnectorSyncJobModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    # ---- write ----------------------------------------------------------

    async def create(self, job_id: str, datasource_id: str, **fields: Any) -> dict[str, Any]:
        """Insert a job row and return it."""
        async with self._session() as session:
            stmt = (
                pg_insert(ConnectorSyncJobModel)
                .values(id=job_id, datasource_id=datasource_id, **fields)
                .returning(ConnectorSyncJobModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def create_exclusive(self, job_id: str, datasource_id: str, **fields: Any) -> dict[str, Any] | None:
        """Insert a job unless the datasource already has a pending or running one.

        One statement, decided by the partial unique index
        ``uq_connector_sync_jobs_active``: of two replicas inserting at the same
        moment exactly one gets its row back, the other gets ``None``.
        """
        async with self._session() as session:
            stmt = (
                pg_insert(ConnectorSyncJobModel)
                .values(id=job_id, datasource_id=datasource_id, **fields)
                .on_conflict_do_nothing(
                    index_elements=["datasource_id"],
                    index_where=text(ACTIVE_JOB_PREDICATE),
                )
                .returning(ConnectorSyncJobModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        """Overwrite the mutable fields of a job. ``None`` values are written as NULL.

        Raises ``LiveSyncJobConflictError`` when the write would make the job live
        (pending or running) again: while its datasource has another live job, or
        after another worker ended this job (a stale-job takeover). A live status is
        only ever written over a live one.
        """
        allowed = {"status", "stats", "error", "worker_id", "heartbeat_at", "started_at", "finished_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get(job_id)
        live_write = updates.get("status") in ACTIVE_STATUSES

        try:
            async with self._session() as session:
                stmt = (
                    update(ConnectorSyncJobModel)
                    .where(ConnectorSyncJobModel.id == job_id)
                    .values(**updates)
                    .returning(ConnectorSyncJobModel)
                )
                if live_write:
                    stmt = stmt.where(ConnectorSyncJobModel.status.in_(ACTIVE_STATUSES))
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None and live_write:
                    ended = await session.execute(
                        select(ConnectorSyncJobModel.status).where(ConnectorSyncJobModel.id == job_id)
                    )
                    if ended.scalar_one_or_none() is not None:
                        raise LiveSyncJobConflictError(job_id)
        except IntegrityError as exc:
            if ACTIVE_JOB_INDEX not in str(exc.orig):
                raise
            raise LiveSyncJobConflictError(job_id) from exc
        if row is None:
            return None
        return self._to_dict(row)


class ConnectorSyncStateRepository(BaseRepository):
    """CRUD operations on the ``connector_sync_state`` table."""

    async def get(self, datasource_id: str) -> dict[str, Any] | None:
        """Return the stored checkpoint document of a datasource."""
        async with self._read_session() as session:
            stmt = select(ConnectorSyncStateModel.state).where(ConnectorSyncStateModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            state = result.scalar_one_or_none()
        return state

    async def create(self, datasource_id: str, state: dict[str, Any]) -> None:
        """Insert or replace the checkpoint document of a datasource."""
        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                pg_insert(ConnectorSyncStateModel)
                .values(datasource_id=datasource_id, state=state, updated_at=now)
                .on_conflict_do_update(
                    index_elements=["datasource_id"],
                    set_={"state": state, "updated_at": now},
                )
            )
            await session.execute(stmt)

    async def delete(self, datasource_id: str) -> bool:
        """Forget the checkpoints of a datasource.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(ConnectorSyncStateModel).where(ConnectorSyncStateModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            return result.rowcount > 0
