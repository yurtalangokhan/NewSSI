"""Datasource repository — CRUD for ``langchain_pg_collection``.

Collection metadata lives in Postgres. All embedding / chunk data is owned
by rag-service — this repository reads it over HTTP rather than opening a
Milvus connection itself (see ``integrations.rag_client``).
"""

from __future__ import annotations

import json
from typing import Any

from error_contract import ConflictError
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from core.observability.logger import get_logger
from infrastructure.db.models.collection import PgCollection
from infrastructure.db.repositories.base import BaseRepository
from integrations.rag_client import fetch_datasource_entities
from integrations.user_service_client import get_current_access_token

logger = get_logger(__name__)


def _parse_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except json.JSONDecodeError:
            return {}
    return {}


class DatasourceRepository(BaseRepository):
    """CRUD for ``langchain_pg_collection`` used by the datasource endpoints.

    Embedding / chunk data lives in Milvus, owned and queried by rag-service
    — NOT read from langchain_pg_embedding, and never via a local Milvus
    connection.
    """

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        return _parse_meta(raw)

    # ---- collection reads -----------------------------------------------

    async def list_datasource_collections(self) -> list[dict[str, Any]]:
        """Return collections that have a ``connector_type`` in their metadata."""
        async with self._read_session() as session:
            stmt = (
                select(PgCollection.uuid, PgCollection.name, PgCollection.cmetadata)
                .where(PgCollection.cmetadata["connector_type"].as_string().isnot(None))
                .order_by(PgCollection.name)
            )
            result = await session.execute(stmt)
            rows = result.all()

        return [
            {
                "uuid": str(r.uuid),
                "name": r.name,
                "cmetadata": self._parse_metadata(r.cmetadata),
                "doc_count": 0,  # derived from chunk_stats or Milvus in the service layer
            }
            for r in rows
        ]

    async def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        """Fetch a single collection by UUID."""
        async with self._read_session() as session:
            stmt = select(PgCollection).where(PgCollection.uuid == collection_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "uuid": str(row.uuid),
            "name": row.name,
            "cmetadata": self._parse_metadata(row.cmetadata),
        }

    async def get_collection_by_name(self, name: str) -> dict[str, Any] | None:
        """Fetch a single collection by name."""
        async with self._read_session() as session:
            stmt = select(PgCollection).where(PgCollection.name == name)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "uuid": str(row.uuid),
            "name": row.name,
            "cmetadata": self._parse_metadata(row.cmetadata),
        }

    # ---- collection writes ----------------------------------------------

    async def create_collection(
        self,
        collection_uuid: str,
        name: str,
        cmetadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Insert a new collection row and return it."""
        try:
            async with self._session() as session:
                stmt = (
                    pg_insert(PgCollection)
                    .values(uuid=collection_uuid, name=name, cmetadata=cmetadata)
                    .returning(PgCollection)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
        except IntegrityError as exc:
            raise ConflictError() from exc
        if row is None:
            return None
        return {
            "uuid": str(row.uuid),
            "name": row.name,
            "cmetadata": self._parse_metadata(row.cmetadata),
        }

    async def update_collection_metadata(
        self,
        collection_id: str,
        cmetadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Overwrite the ``cmetadata`` JSON for a collection."""
        async with self._session() as session:
            stmt = (
                update(PgCollection)
                .where(PgCollection.uuid == collection_id)
                .values(cmetadata=cmetadata)
                .returning(PgCollection)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "uuid": str(row.uuid),
            "name": row.name,
            "cmetadata": self._parse_metadata(row.cmetadata),
        }

    async def update_collection(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        cmetadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update ``name`` and/or ``cmetadata`` for a collection."""
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if cmetadata is not None:
            values["cmetadata"] = cmetadata
        if not values:
            return await self.get_collection(collection_id)

        async with self._session() as session:
            stmt = (
                update(PgCollection).where(PgCollection.uuid == collection_id).values(**values).returning(PgCollection)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "uuid": str(row.uuid),
            "name": row.name,
            "cmetadata": self._parse_metadata(row.cmetadata),
        }

    async def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection by UUID.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(PgCollection).where(PgCollection.uuid == collection_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    # ---- embedding reads (rag-service / Milvus) --------------------------

    async def count_embeddings(self, collection_id: str) -> int:
        """Return the number of entities stored in Milvus for this collection."""
        result = await fetch_datasource_entities(
            collection_id,
            limit=0,
            access_token=get_current_access_token(),
        )
        return int(result.get("count", 0))

    async def get_paginated_embeddings(
        self,
        collection_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return paginated chunks from Milvus for a collection."""
        result = await fetch_datasource_entities(
            collection_id,
            limit=limit,
            offset=offset,
            access_token=get_current_access_token(),
        )

        return [
            {
                "document": entity.get("content", ""),
                "cmetadata": _parse_meta(entity.get("metadata")),
            }
            for entity in result.get("entities", [])
        ]
