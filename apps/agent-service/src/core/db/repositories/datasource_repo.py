"""Datasource repository — CRUD for ``langchain_pg_collection``.

Collection metadata lives in Postgres.
All embedding / chunk data is stored and queried from Milvus.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.models.collection import PgCollection
from core.db.repositories.base import BaseRepository
from core.env import env
from core.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Milvus helpers (mirrors agent-service/src/agents/tools.py)
# ---------------------------------------------------------------------------


def _to_milvus_collection_name(raw_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", (raw_name or "").strip())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "collection"
    if name[0].isdigit():
        name = f"c_{name}"
    return name


def _get_milvus_connection_args() -> dict:
    return {
        "host": env.get("MILVUS_HOST", "localhost"),
        "port": env.get("MILVUS_PORT", "9765"),
        "user": env.get("MILVUS_USER", ""),
        "password": env.get("MILVUS_PASSWORD", ""),
        "secure": False,
    }


def _parse_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) or {}
        except Exception:
            return {}
    return {}


def _get_milvus_store(collection_name: str):
    """Return a LangChain Milvus store for the given raw collection name."""
    from langchain_community.vectorstores import Milvus

    from agents.tools import get_embeddings  # noqa: PLC0415

    milvus_name = _to_milvus_collection_name(collection_name)
    return Milvus(
        embedding_function=get_embeddings(),
        collection_name=milvus_name,
        connection_args=_get_milvus_connection_args(),
        auto_id=True,
        metadata_field="metadata",
    )


class DatasourceRepository(BaseRepository):
    """CRUD for ``langchain_pg_collection`` used by the datasource endpoints.

    Embedding data is read/written from/to Milvus — NOT from langchain_pg_embedding.
    """

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        return _parse_meta(raw)

    # ---- collection reads -----------------------------------------------

    async def list_datasource_collections(self) -> list[dict[str, Any]]:
        """Return collections that have a ``connector_type`` in their metadata."""
        async with self._session() as session:
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
                "doc_count": 0,  # derived from chunk_stats or Milvus in controller
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
                .values(uuid=collection_uuid, name=name, cmetadata=cmetadata)
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
        """Delete a collection by UUID.  Returns ``True`` if a row was removed."""
        async with self._session() as session:
            stmt = delete(PgCollection).where(PgCollection.uuid == collection_id)
            result = await session.execute(stmt)
            return result.rowcount > 0

    # ---- embedding reads (Milvus) ---------------------------------------

    async def count_embeddings(self, collection_id: str) -> int:
        """Return the number of entities stored in Milvus for this collection."""
        row = await self.get_collection(collection_id)
        if not row:
            return 0
        store = _get_milvus_store(row["name"])
        if store.col is None:
            return 0
        try:
            return await asyncio.to_thread(lambda: store.col.num_entities)
        except Exception as exc:
            logger.warning("Milvus count failed for %r: %s", collection_id, exc)
            return 0

    async def get_paginated_embeddings(
        self,
        collection_id: str,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return paginated chunks from Milvus for a collection."""
        row = await self.get_collection(collection_id)
        if not row:
            return []
        store = _get_milvus_store(row["name"])
        if store.col is None:
            return []

        def _query():
            return store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._text_field, store._metadata_field],
                limit=limit,
                offset=offset,
            )

        try:
            rows = await asyncio.to_thread(_query)
        except Exception as exc:
            logger.warning("Milvus paginated query failed for %r: %s", collection_id, exc)
            return []

        return [
            {
                "document": r.get(store._text_field, ""),
                "cmetadata": _parse_meta(r.get(store._metadata_field)),
            }
            for r in rows
        ]

    async def delete_embeddings(self, collection_id: str) -> int:
        """Delete all embeddings from Milvus for a collection."""
        row = await self.get_collection(collection_id)
        if not row:
            return 0
        store = _get_milvus_store(row["name"])
        if store.col is None:
            return 0
        try:
            count_before = await asyncio.to_thread(lambda: store.col.num_entities)
            await asyncio.to_thread(store.col.drop)
            logger.info("Dropped Milvus collection %r (%d entities).", row["name"], count_before)
            return count_before
        except Exception as exc:
            logger.warning("Milvus delete_embeddings failed for %r: %s", collection_id, exc)
            return 0

    async def get_embedding_stats(self, collection_id: str) -> dict[str, int]:
        """Return aggregate chunk statistics from Milvus."""
        row = await self.get_collection(collection_id)
        if not row:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}
        store = _get_milvus_store(row["name"])
        if store.col is None:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}

        def _query():
            return store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._text_field],
                limit=10_000,
            )

        try:
            rows = await asyncio.to_thread(_query)
        except Exception:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}

        if not rows:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}

        chunk_count = len(rows)
        total_chars = sum(len(r.get(store._text_field, "")) for r in rows)
        avg_chars = total_chars // chunk_count if chunk_count else 0
        avg_tokens = max(1, avg_chars // 4) if avg_chars else 0
        return {
            "chunk_count": chunk_count,
            "avg_chunk_chars": avg_chars,
            "avg_chunk_tokens": avg_tokens,
        }
