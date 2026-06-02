"""Thread repository — typed CRUD for the ``thread`` table."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import cast, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.thread import ThreadModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _ensure_datetime(val: Any) -> datetime:
    """Convert ISO-format strings to ``datetime``; pass through actual datetimes."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.now(UTC)


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
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return None

        async with self._session() as session:
            stmt = select(ThreadModel).where(
                ThreadModel.thread_id == parsed_thread_id
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
                        "project_id": values["project_id"],
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

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread by UUID.  Returns ``True`` if a row was removed."""
        parsed_thread_id = _parse_thread_id(thread_id)
        if parsed_thread_id is None:
            return False

        async with self._session() as session:
            stmt = delete(ThreadModel).where(
                ThreadModel.thread_id == parsed_thread_id
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
