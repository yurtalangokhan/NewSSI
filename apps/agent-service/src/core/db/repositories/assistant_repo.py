"""Assistant repository — typed CRUD for the ``assistant`` table."""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.assistant import AssistantModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _ensure_datetime(val: Any) -> datetime:
    """Convert ISO-format strings to ``datetime``; pass through actual datetimes."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.now(UTC)


class AssistantRepository(BaseRepository):
    """CRUD operations on the ``assistant`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: AssistantModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "assistant_id": str(row.assistant_id),
            "graph_id": row.graph_id,
            "name": row.name or row.graph_id,
            "config": row.config or {},
            "metadata": row.metadata_ or {},
            "version": row.version,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _validate_uuid(value: str) -> bool:
        """Return ``True`` if *value* is a valid UUID string."""
        try:
            _uuid.UUID(str(value))
            return True
        except ValueError:
            return False

    # ---- read -----------------------------------------------------------

    async def list_assistants(self) -> list[dict[str, Any]]:
        """Return all assistants ordered by most recently updated."""
        async with self._session() as session:
            stmt = select(AssistantModel).order_by(AssistantModel.updated_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    async def get_assistant(self, assistant_id: str) -> dict[str, Any] | None:
        """Fetch a single assistant by UUID."""
        if not self._validate_uuid(assistant_id):
            return None
        async with self._session() as session:
            stmt = select(AssistantModel).where(AssistantModel.assistant_id == assistant_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    # ---- write ----------------------------------------------------------

    async def save_assistant(self, assistant: dict[str, Any]) -> dict[str, Any] | None:
        """Upsert an assistant (insert or update on conflict).

        Returns the saved row as a dict.
        """
        now = datetime.now(UTC)
        values = {
            "assistant_id": assistant["assistant_id"],
            "graph_id": assistant["graph_id"],
            "name": assistant.get("name"),
            "config": assistant.get("config", {}),
            "metadata_": assistant.get("metadata", {}),
            "created_at": _ensure_datetime(assistant.get("created_at", now)),
            "updated_at": _ensure_datetime(assistant.get("updated_at", now)),
        }
        async with self._session() as session:
            stmt = (
                pg_insert(AssistantModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["assistant_id"],
                    set_={
                        "name": values["name"],
                        "config": values["config"],
                        "metadata": values["metadata_"],
                        "updated_at": values["updated_at"],
                    },
                )
                .returning(AssistantModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def update_assistant(
        self,
        assistant_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Merge *updates* into an existing assistant.

        Supports partial updates for ``name``, ``config``, and ``metadata``.
        """
        current = await self.get_assistant(assistant_id)
        if current is None:
            return None

        if "config" in updates:
            current["config"] = updates["config"]
        if "metadata" in updates:
            current["metadata"].update(updates["metadata"])
        if "name" in updates:
            current["name"] = updates["name"]

        current["updated_at"] = datetime.now(UTC).isoformat()
        return await self.save_assistant(current)

    async def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant by UUID.  Returns ``True`` if a row was removed."""
        if not self._validate_uuid(assistant_id):
            return False
        async with self._session() as session:
            stmt = delete(AssistantModel).where(AssistantModel.assistant_id == assistant_id)
            result = await session.execute(stmt)
            return result.rowcount > 0
