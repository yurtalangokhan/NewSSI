"""Datasource connection repository — typed CRUD for ``datasource_connections``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from infrastructure.db.models.datasource_connection import DatasourceConnectionModel
from infrastructure.db.repositories.base import BaseRepository


class DatasourceConnectionRepository(BaseRepository):
    """CRUD operations on the ``datasource_connections`` table."""

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _to_dict(row: DatasourceConnectionModel) -> dict[str, Any]:
        """Convert an ORM row to a JSON-friendly dict."""
        return {
            "datasource_id": str(row.datasource_id),
            "connector_name": row.connector_name,
            "config_id": str(row.config_id),
            "owner_user_id": row.owner_user_id,
            "catalog": row.catalog or {},
            "update_graph_rag": row.update_graph_rag,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ---- read -----------------------------------------------------------

    async def get(self, datasource_id: str) -> dict[str, Any] | None:
        """Return the connection of a datasource."""
        async with self._read_session() as session:
            stmt = select(DatasourceConnectionModel).where(DatasourceConnectionModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def list_all(self) -> list[dict[str, Any]]:
        """Return all connections ordered by creation date."""
        async with self._read_session() as session:
            stmt = select(DatasourceConnectionModel).order_by(DatasourceConnectionModel.created_at)
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [self._to_dict(r) for r in rows]

    # ---- write ----------------------------------------------------------

    async def create(
        self,
        datasource_id: str,
        connector_name: str,
        config_id: str,
        owner_user_id: str,
        catalog: dict[str, Any],
        *,
        update_graph_rag: bool = False,
    ) -> dict[str, Any]:
        """Insert or replace the connection of a datasource and return it."""
        now = datetime.now(UTC)
        values = {
            "connector_name": connector_name,
            "config_id": config_id,
            "owner_user_id": owner_user_id,
            "catalog": catalog,
            "update_graph_rag": update_graph_rag,
            "updated_at": now,
        }
        async with self._session() as session:
            stmt = (
                pg_insert(DatasourceConnectionModel)
                .values(datasource_id=datasource_id, created_at=now, **values)
                .on_conflict_do_update(index_elements=["datasource_id"], set_=values)
                .returning(DatasourceConnectionModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one()
        return self._to_dict(row)

    async def update(self, datasource_id: str, **fields: Any) -> dict[str, Any] | None:
        """Update fields on a connection row.

        Only the allowed field set is accepted; unknown keys are ignored.
        """
        allowed = {"connector_name", "config_id", "owner_user_id", "catalog", "update_graph_rag"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get(datasource_id)

        updates["updated_at"] = datetime.now(UTC)

        async with self._session() as session:
            stmt = (
                update(DatasourceConnectionModel)
                .where(DatasourceConnectionModel.datasource_id == datasource_id)
                .values(**updates)
                .returning(DatasourceConnectionModel)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_dict(row)

    async def delete(self, datasource_id: str) -> bool:
        """Delete a connection.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(DatasourceConnectionModel).where(DatasourceConnectionModel.datasource_id == datasource_id)
            result = await session.execute(stmt)
            return result.rowcount > 0
