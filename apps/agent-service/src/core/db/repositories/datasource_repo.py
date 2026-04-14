"""Datasource repository — typed CRUD for ``langchain_pg_collection`` / ``langchain_pg_embedding``."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.collection import PgCollection, PgEmbedding
from core.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DatasourceRepository(BaseRepository):
    """Queries on the ``langchain_pg_collection`` and
    ``langchain_pg_embedding`` tables used by the datasource endpoints.
    """

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        """Normalise ``cmetadata`` from the DB into a plain ``dict``."""
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                return json.loads(raw) or {}
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(raw, dict):
            return raw.copy()
        try:
            return dict(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    # ---- collection reads -----------------------------------------------

    async def list_datasource_collections(self) -> list[dict[str, Any]]:
        """Return collections that have a ``connector_type`` in their metadata,
        together with a document count per collection.
        """
        async with self._session() as session:
            stmt = (
                select(
                    PgCollection.uuid,
                    PgCollection.name,
                    PgCollection.cmetadata,
                    func.count(PgEmbedding.id).label("doc_count"),
                )
                .outerjoin(PgEmbedding, PgEmbedding.collection_id == PgCollection.uuid)
                .where(PgCollection.cmetadata["connector_type"].as_string().isnot(None))
                .group_by(PgCollection.uuid, PgCollection.name)
            )
            result = await session.execute(stmt)
            rows = result.all()

        return [
            {
                "uuid": str(r.uuid),
                "name": r.name,
                "cmetadata": self._parse_metadata(r.cmetadata),
                "doc_count": r.doc_count,
            }
            for r in rows
        ]

    async def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        """Fetch a single collection by UUID."""
        async with self._session() as session:
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
        async with self._session() as session:
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
        async with self._session() as session:
            stmt = (
                pg_insert(PgCollection)
                .values(
                    uuid=collection_uuid,
                    name=name,
                    cmetadata=cmetadata,
                )
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
        """Update ``name`` and/or ``cmetadata`` for a collection.

        Only the provided fields are updated; ``None`` values are skipped.
        """
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if cmetadata is not None:
            values["cmetadata"] = cmetadata
        if not values:
            return await self.get_collection(collection_id)

        async with self._session() as session:
            stmt = (
                update(PgCollection)
                .where(PgCollection.uuid == collection_id)
                .values(**values)
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

    async def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection by UUID (cascades to embeddings).
        Returns ``True`` if a row was removed.
        """
        async with self._session() as session:
            stmt = delete(PgCollection).where(PgCollection.uuid == collection_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    # ---- embedding reads ------------------------------------------------

    async def count_embeddings(self, collection_id: str) -> int:
        """Return the number of embedding rows for a collection."""
        async with self._session() as session:
            stmt = (
                select(func.count(PgEmbedding.id))
                .where(PgEmbedding.collection_id == collection_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_paginated_embeddings(
        self,
        collection_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return paginated embedding rows for a collection."""
        async with self._session() as session:
            stmt = (
                select(PgEmbedding.document, PgEmbedding.cmetadata)
                .where(PgEmbedding.collection_id == collection_id)
                .order_by(PgEmbedding.id)
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            rows = result.all()

        return [
            {
                "document": r.document or "",
                "cmetadata": self._parse_metadata(r.cmetadata),
            }
            for r in rows
        ]

    async def delete_embeddings(self, collection_id: str) -> int:
        """Delete all embeddings for a collection.  Returns rows deleted."""
        async with self._session() as session:
            stmt = delete(PgEmbedding).where(
                PgEmbedding.collection_id == collection_id
            )
            result = await session.execute(stmt)
            return result.rowcount

    async def get_embedding_stats(self, collection_id: str) -> dict[str, int]:
        """Return aggregate chunk statistics for a collection.

        Returns ``chunk_count``, ``avg_chunk_chars``, and ``avg_chunk_tokens``.
        """
        async with self._session() as session:
            stmt = select(
                func.count(PgEmbedding.id).label("chunk_count"),
                func.coalesce(func.avg(func.length(PgEmbedding.document)), 0).label("avg_chars"),
            ).where(PgEmbedding.collection_id == collection_id)
            result = await session.execute(stmt)
            row = result.one()

        chunk_count = row.chunk_count or 0
        avg_chars = int(row.avg_chars) if row.avg_chars else 0
        avg_tokens = max(1, int(avg_chars / 4)) if avg_chars else 0
        return {
            "chunk_count": chunk_count,
            "avg_chunk_chars": avg_chars,
            "avg_chunk_tokens": avg_tokens,
        }
