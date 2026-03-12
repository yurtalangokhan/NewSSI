"""Airbyte mapping repository — typed CRUD for ``datasource_airbyte_mapping``."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.airbyte_mapping import AirbyteMappingModel
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AirbyteMappingRepository(BaseRepository):
    """CRUD operations on the ``datasource_airbyte_mapping`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: AirbyteMappingModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "datasource_id": str(row.datasource_id),
            "airbyte_source_id": row.airbyte_source_id,
            "airbyte_connection_id": row.airbyte_connection_id,
            "airbyte_destination_id": row.airbyte_destination_id,
            "update_graph_rag": row.update_graph_rag,
            "last_processed_job_id": row.last_processed_job_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ---- read -----------------------------------------------------------

    async def get(self, datasource_id: str) -> dict[str, Any] | None:
        """Return the mapping for a datasource."""
        async with self._session() as session:
            stmt = select(AirbyteMappingModel).where(
                AirbyteMappingModel.datasource_id == datasource_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_all(self) -> list[dict[str, Any]]:
        """Return all mappings ordered by creation date."""
        async with self._session() as session:
            stmt = select(AirbyteMappingModel).order_by(
                AirbyteMappingModel.created_at
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    # ---- write ----------------------------------------------------------

    async def create(
        self,
        datasource_id: str,
        airbyte_source_id: str,
        airbyte_connection_id: str,
        airbyte_destination_id: str,
        *,
        update_graph_rag: bool = False,
    ) -> dict[str, Any]:
        """Insert or upsert a mapping row and return it."""
        now = datetime.now(timezone.utc)
        async with self._session() as session:
            stmt = (
                pg_insert(AirbyteMappingModel)
                .values(
                    datasource_id=datasource_id,
                    airbyte_source_id=airbyte_source_id,
                    airbyte_connection_id=airbyte_connection_id,
                    airbyte_destination_id=airbyte_destination_id,
                    update_graph_rag=update_graph_rag,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["datasource_id"],
                    set_={
                        "airbyte_source_id": airbyte_source_id,
                        "airbyte_connection_id": airbyte_connection_id,
                        "airbyte_destination_id": airbyte_destination_id,
                        "update_graph_rag": update_graph_rag,
                        "updated_at": now,
                    },
                )
                .returning(AirbyteMappingModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def update(
        self,
        datasource_id: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        """Update fields on a mapping row.

        Only the allowed field set is accepted; unknown keys are ignored.
        """
        allowed = {
            "airbyte_source_id",
            "airbyte_connection_id",
            "airbyte_destination_id",
            "update_graph_rag",
            "last_processed_job_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get(datasource_id)

        updates["updated_at"] = datetime.now(timezone.utc)

        async with self._session() as session:
            stmt = (
                update(AirbyteMappingModel)
                .where(AirbyteMappingModel.datasource_id == datasource_id)
                .values(**updates)
                .returning(AirbyteMappingModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def delete(self, datasource_id: str) -> bool:
        """Delete a mapping.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(AirbyteMappingModel).where(
                AirbyteMappingModel.datasource_id == datasource_id
            )
            result = await session.execute(stmt)
            return result.rowcount > 0
