"""Thread repository — typed CRUD for the ``thread`` table."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import cast, delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.thread import ThreadModel
from core.db.repositories.base import BaseRepository
from core.logger import get_logger
from core.run_kinds import DEFAULT_RUN_KIND, RunKind

logger = get_logger(__name__)


def _run_kind_where(stmt: Any, run_kinds: Sequence[str] | None) -> Any:
    """Constrain a thread query to ``run_kinds``.

    ``None`` means no filter. When the caller wants ``production`` threads, the
    legacy ``NULL`` run_kind (rows written before the column existed) counts as
    production too.
    """
    if run_kinds is None:
        return stmt
    if RunKind.PRODUCTION in run_kinds:
        return stmt.where(ThreadModel.run_kind.in_(run_kinds) | ThreadModel.run_kind.is_(None))
    return stmt.where(ThreadModel.run_kind.in_(run_kinds))


def _ensure_datetime(val: Any) -> datetime:
    """Convert ISO-format strings to ``datetime``; pass through actual datetimes."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.now(UTC)


def _ensure_optional_datetime(val: Any) -> datetime | None:
    """Convert an optional ISO-format timestamp to ``datetime``."""
    if val is None:
        return None
    return _ensure_datetime(val)


def _parse_thread_id(thread_id: str) -> UUID | None:
    """Return a UUID for valid thread ids and ``None`` for malformed values."""
    try:
        return UUID(thread_id)
    except (TypeError, ValueError, AttributeError):
        logger.warning("Skipping thread lookup for malformed thread_id=%r", thread_id)
        return None


class ThreadRepository(BaseRepository):
    """CRUD operations on the ``thread`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _resolve_project_id(row: ThreadModel) -> int | None:
        """Read project_id from the canonical column, falling back to legacy metadata."""
        if row.project_id is not None:
            return row.project_id

        metadata = row.metadata_ or {}
        metadata_project_id = metadata.get("project_id")
        if metadata_project_id is None:
            return None

        try:
            return int(metadata_project_id)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid metadata project_id=%r for thread_id=%s",
                metadata_project_id,
                row.thread_id,
            )
            return None

    @staticmethod
    def _to_dict(row: ThreadModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "thread_id": str(row.thread_id),
            "metadata": row.metadata_ or {},
            "status": row.status or "idle",
            "project_id": ThreadRepository._resolve_project_id(row),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
            "last_accessed_at": row.last_accessed_at.isoformat() if row.last_accessed_at else None,
            "run_kind": row.run_kind or DEFAULT_RUN_KIND.value,
        }

    # ---- read -----------------------------------------------------------

    async def list_threads(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        metadata_filter: dict[str, Any] | None = None,
        run_kinds: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return threads ordered by most recently updated.

        If *metadata_filter* is provided, only threads whose ``metadata``
        JSONB column contains the given key/value pairs are returned
        (PostgreSQL ``@>`` operator).
        """
        async with self._session() as session:
            stmt = select(ThreadModel)
            if metadata_filter:
                stmt = stmt.where(ThreadModel.metadata_.op("@>")(cast(metadata_filter, JSONB)))
            stmt = _run_kind_where(stmt, run_kinds)
            stmt = stmt.order_by(ThreadModel.updated_at.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def list_chat_sessions_by_activity(
        self,
        *,
        page_size: int = 100,
        before_activity: str | datetime | None = None,
        before_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        run_kinds: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return chat sessions ordered by conversational activity.

        This chat-specific query deliberately does not alter the SDK-compatible
        ``list_threads`` ordering.  When both cursor values are supplied, it
        returns the page immediately following that activity key.
        """
        activity_at = func.coalesce(ThreadModel.last_message_at, ThreadModel.created_at)
        stmt = select(ThreadModel)
        if metadata_filter:
            stmt = stmt.where(ThreadModel.metadata_.op("@>")(cast(metadata_filter, JSONB)))
        stmt = _run_kind_where(stmt, run_kinds)

        parsed_before_id = _parse_thread_id(before_id) if before_id else None
        if before_activity is not None and parsed_before_id is not None:
            stmt = stmt.where(
                tuple_(activity_at, ThreadModel.thread_id)
                < tuple_(_ensure_datetime(before_activity), parsed_before_id)
            )

        stmt = stmt.order_by(activity_at.desc(), ThreadModel.thread_id.desc()).limit(page_size)
        async with self._session() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Fetch a single thread by UUID."""
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return None

        async with self._session() as session:
            stmt = select(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    # ---- write ----------------------------------------------------------

    async def add_thread(self, thread: dict[str, Any]) -> dict[str, Any] | None:
        """Upsert a thread (insert or update on conflict).

        Returns the saved row as a dict.
        """
        now = datetime.now(UTC)
        values = {
            "thread_id": thread["thread_id"],
            "metadata_": thread.get("metadata", {}),
            "status": thread.get("status", "idle"),
            "project_id": thread.get("project_id")
            if thread.get("project_id") is not None
            else (thread.get("metadata", {}) or {}).get("project_id"),
            "created_at": _ensure_datetime(thread.get("created_at", now)),
            "updated_at": _ensure_datetime(thread.get("updated_at", now)),
            "run_kind": thread.get("run_kind") or DEFAULT_RUN_KIND.value,
        }
        activity_fields = ("last_message_at", "last_accessed_at")
        for field in activity_fields:
            if field in thread:
                values[field] = _ensure_optional_datetime(thread[field])

        conflict_updates = {
            "metadata": values["metadata_"],
            "updated_at": values["updated_at"],
            "status": values["status"],
            "project_id": values["project_id"],
        }
        if "run_kind" in thread:
            conflict_updates["run_kind"] = values["run_kind"]
        for field in activity_fields:
            if field in values:
                conflict_updates[field] = values[field]

        async with self._session() as session:
            stmt = (
                pg_insert(ThreadModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_=conflict_updates,
                )
                .returning(ThreadModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def update_thread(
        self,
        thread_id: str,
        updates: dict[str, Any],
        update_timestamp: bool = True,
    ) -> dict[str, Any] | None:
        """Merge *updates* into an existing thread.

        Supports partial updates for ``metadata`` and ``status``.
        """
        current = await self.get_thread(thread_id)
        if current is None:
            return None

        if "metadata" in updates and updates["metadata"]:
            current["metadata"].update(updates["metadata"])
        if "status" in updates:
            current["status"] = updates["status"]
        if "project_id" in updates:
            current["project_id"] = updates["project_id"]

        if update_timestamp:
            current["updated_at"] = datetime.now(UTC).isoformat()
        return await self.add_thread(current)

    async def mark_message_activity(self, thread_id: str) -> dict[str, Any] | None:
        """Record accepted user-message activity without rewriting thread metadata."""
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return None

        now = datetime.now(UTC)
        async with self._session() as session:
            stmt = (
                update(ThreadModel)
                .where(ThreadModel.thread_id == parsed_thread_id)
                .values(last_message_at=now, updated_at=now)
                .returning(ThreadModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def mark_accessed(self, thread_id: str) -> dict[str, Any] | None:
        """Record a read without rewriting thread metadata or activity."""
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return None

        async with self._session() as session:
            stmt = (
                update(ThreadModel)
                .where(ThreadModel.thread_id == parsed_thread_id)
                .values(last_accessed_at=datetime.now(UTC))
                .returning(ThreadModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row is not None else None

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread by UUID.  Returns ``True`` if a row was removed."""
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return False

        async with self._session() as session:
            stmt = delete(ThreadModel).where(ThreadModel.thread_id == parsed_thread_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    async def delete_threads_older_than(
        self,
        *,
        run_kind: str,
        older_than: datetime,
    ) -> list[str]:
        """Bulk-delete threads of the given run_kind whose created_at predates the cutoff.

        Returns the list of deleted thread_ids as strings.
        """
        async with self._session() as session:
            select_stmt = select(ThreadModel.thread_id).where(
                ThreadModel.run_kind == run_kind,
                ThreadModel.created_at < older_than,
            )
            res = await session.execute(select_stmt)
            thread_ids = [str(tid) for tid in res.scalars().all()]
            if not thread_ids:
                return []

            delete_stmt = delete(ThreadModel).where(
                ThreadModel.run_kind == run_kind,
                ThreadModel.created_at < older_than,
            )
            await session.execute(delete_stmt)
            return thread_ids
