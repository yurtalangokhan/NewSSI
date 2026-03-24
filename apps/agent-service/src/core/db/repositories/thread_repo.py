"""Thread repository — typed CRUD for the ``thread`` table."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, cast
from sqlalchemy.dialects.postgresql import insert as pg_insert, JSONB

from core.db.models.thread import ThreadModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _ensure_datetime(val: Any) -> datetime:
    """Convert ISO-format strings to ``datetime``; pass through actual datetimes."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.now(timezone.utc)


class ThreadRepository(BaseRepository):
    """CRUD operations on the ``thread`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: ThreadModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "thread_id": str(row.thread_id),
            "metadata": row.metadata_ or {},
            "status": row.status or "idle",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ---- read -----------------------------------------------------------

    async def list_threads(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return threads ordered by most recently updated.

        If *metadata_filter* is provided, only threads whose ``metadata``
        JSONB column contains the given key/value pairs are returned
        (PostgreSQL ``@>`` operator).
        """
        async with self._session() as session:
            stmt = select(ThreadModel)
            if metadata_filter:
                stmt = stmt.where(
                    ThreadModel.metadata_.op("@>")(cast(metadata_filter, JSONB))
                )
            stmt = (
                stmt.order_by(ThreadModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        """Fetch a single thread by UUID."""
        async with self._session() as session:
            stmt = select(ThreadModel).where(
                ThreadModel.thread_id == thread_id
            )
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
        now = datetime.now(timezone.utc)
        values = {
            "thread_id": thread["thread_id"],
            "metadata_": thread.get("metadata", {}),
            "status": thread.get("status", "idle"),
            "created_at": _ensure_datetime(thread.get("created_at", now)),
            "updated_at": _ensure_datetime(thread.get("updated_at", now)),
        }
        async with self._session() as session:
            stmt = (
                pg_insert(ThreadModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_={
                        "metadata": values["metadata_"],
                        "updated_at": values["updated_at"],
                        "status": values["status"],
                    },
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

        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.add_thread(current)

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread by UUID.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(ThreadModel).where(
                ThreadModel.thread_id == thread_id
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
