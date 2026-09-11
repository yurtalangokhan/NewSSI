"""Document / embedding repository — typed queries on ``langchain_pg_embedding``."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from langconnect.database.postgres.models import PgCollection, PgEmbedding
from langconnect.database.postgres.repositories.base import BaseRepository
from langconnect.observability import get_logger

logger = get_logger(__name__)


class DocumentRepository(BaseRepository):
    """Query and mutate rows in ``langchain_pg_embedding``."""

    def __init__(self, collection_id: str, user_id: str) -> None:
        self.collection_id = collection_id
        self.user_id = user_id

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                return json.loads(raw) or {}
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(raw, dict):
            return raw.copy()
        return {}

    # ---- read -----------------------------------------------------------

    async def list_documents(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List one representative chunk per unique ``file_id``."""
        async with self._session() as session:
            emb = aliased(PgEmbedding, name="emb")
            col = aliased(PgCollection, name="col")

            # Sub-query: distinct on file_id
            file_id_expr = emb.cmetadata["file_id"].as_string()

            unique_sub = (
                select(
                    emb.id.label("uid"),
                    file_id_expr.label("file_id"),
                )
                .join(col, emb.collection_id == col.uuid)
                .where(col.uuid == self.collection_id)
                .where(col.cmetadata["owner_id"].as_string() == self.user_id)
                .where(file_id_expr.isnot(None))
                .distinct(file_id_expr)
                .order_by(file_id_expr, emb.id)
                .subquery("ufc")
            )

            # Main query — join back to get full row
            main_emb = aliased(PgEmbedding, name="main_emb")
            stmt = (
                select(main_emb)
                .join(unique_sub, main_emb.id == unique_sub.c.uid)
                .order_by(unique_sub.c.file_id)
                .limit(limit)
                .offset(offset)
            )

            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            {
                "id": self._parse_metadata(r.cmetadata).get("file_id") or str(r.id),
                "content": r.document,
                "metadata": self._parse_metadata(r.cmetadata),
                "collection_id": str(self.collection_id),
            }
            for r in rows
        ]

    async def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Fetch a single embedding/chunk by UUID, verifying ownership."""
        async with self._session() as session:
            emb = aliased(PgEmbedding, name="e")
            col = aliased(PgCollection, name="c")

            stmt = (
                select(emb)
                .join(col, emb.collection_id == col.uuid)
                .where(emb.id == document_id)
                .where(col.cmetadata["owner_id"].as_string() == self.user_id)
                .where(col.uuid == self.collection_id)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None
        return {
            "id": row.id,
            "content": row.document,
            "metadata": self._parse_metadata(row.cmetadata),
        }

    async def count_documents(self) -> int:
        """Count distinct file_ids (i.e. documents) in this collection."""
        async with self._session() as session:
            emb = aliased(PgEmbedding, name="emb")
            col = aliased(PgCollection, name="col")

            file_id_expr = emb.cmetadata["file_id"].as_string()

            stmt = (
                select(func.count(distinct(file_id_expr)))
                .join(col, emb.collection_id == col.uuid)
                .where(col.uuid == self.collection_id)
                .where(col.cmetadata["owner_id"].as_string() == self.user_id)
                .where(file_id_expr.isnot(None))
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def list_chunks_by_file_id(self, file_id: str) -> list[dict[str, Any]]:
        """List all chunks for a specific file by its file_id."""
        async with self._session() as session:
            emb = aliased(PgEmbedding, name="e")
            col = aliased(PgCollection, name="c")

            stmt = (
                select(emb)
                .join(col, emb.collection_id == col.uuid)
                .where(emb.cmetadata["file_id"].as_string() == file_id)
                .where(col.cmetadata["owner_id"].as_string() == self.user_id)
                .where(col.uuid == self.collection_id)
                .order_by(emb.id)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            {
                "id": str(r.id),
                "content": r.document,
                "metadata": self._parse_metadata(r.cmetadata),
            }
            for r in rows
        ]

    # ---- write ----------------------------------------------------------

    async def upsert_documents(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> int:
        """Upsert chunk metadata rows into ``langchain_pg_embedding``.

        This keeps Postgres-backed listing/chunk APIs functional when vectors are
        stored in Milvus.
        """
        if not (len(ids) == len(documents) == len(metadatas)):
            raise ValueError("ids, documents, and metadatas must have equal length")

        if not ids:
            return 0

        rows = [
            {
                "id": str(doc_id),
                "collection_id": uuid.UUID(self.collection_id),
                "document": doc,
                "cmetadata": metadata or {},
            }
            for doc_id, doc, metadata in zip(ids, documents, metadatas, strict=True)
        ]

        async with self._session() as session:
            stmt = pg_insert(PgEmbedding).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[PgEmbedding.id],
                set_={
                    "collection_id": stmt.excluded.collection_id,
                    "document": stmt.excluded.document,
                    "cmetadata": stmt.excluded.cmetadata,
                },
            )
            await session.execute(stmt)

        return len(rows)

    async def delete_by_file_id(self, file_id: str) -> int:
        """Delete embeddings whose ``cmetadata->>'file_id'`` matches.

        With Milvus as the vector backend, also deletes vectors from Milvus
        using an expr filter on the metadata.file_id field.

        Returns:
            Number of rows deleted from Postgres.
        """
        from langconnect import config
        from langconnect.database.connection import get_vectorstore

        # If using Milvus, delete vectors from Milvus first (best-effort)
        if config.VECTOR_DB_PROVIDER.lower() != "pgvector":
            table_id = await self.get_collection_table_name()
            if table_id:
                try:
                    milvus_store = get_vectorstore(collection_name=table_id)
                    # expr-based delete on metadata JSON field
                    milvus_store.delete(expr=f'metadata["file_id"] == "{file_id}"')
                    logger.info(
                        "Deleted Milvus vectors for file %r in collection %r.",
                        file_id,
                        table_id,
                    )
                except Exception as exc:
                    logger.warning("Milvus delete failed for file %r: %s", file_id, exc)

        async with self._session() as session:
            col = aliased(PgCollection, name="c")

            # We need a correlated subquery for the ownership check
            owner_sub = (
                select(col.uuid)
                .where(col.uuid == self.collection_id)
                .where(col.cmetadata["owner_id"].as_string() == self.user_id)
                .correlate()
                .scalar_subquery()
            )

            stmt = (
                delete(PgEmbedding)
                .where(PgEmbedding.collection_id == owner_sub)
                .where(PgEmbedding.cmetadata["file_id"].as_string() == file_id)
            )
            result = await session.execute(stmt)
            deleted = result.rowcount
            logger.info("Deleted %d embeddings for file %r.", deleted, file_id)
            return deleted

    # ---- graph-rag helpers ----------------------------------------------

    async def get_collection_table_name(self) -> str | None:
        """Return the collection ``name`` (table_id) used as vector collection key."""
        async with self._session() as session:
            stmt = select(PgCollection.name).where(
                PgCollection.uuid == self.collection_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def fetch_all_chunks(self) -> list[dict[str, Any]]:
        """Fetch all document chunks for a collection (used by graph build)."""
        async with self._session() as session:
            stmt = (
                select(PgEmbedding.id, PgEmbedding.document, PgEmbedding.cmetadata)
                .where(PgEmbedding.collection_id == self.collection_id)
                .order_by(PgEmbedding.id)
            )
            result = await session.execute(stmt)
            rows = result.all()

        chunks: list[dict[str, Any]] = []
        for r in rows:
            metadata = self._parse_metadata(r.cmetadata)
            chunks.append(
                {
                    "id": str(r.id),
                    "content": r.document or "",
                    "metadata": metadata,
                }
            )
        logger.info(
            "Fetched %d chunks from collection %s", len(chunks), self.collection_id
        )
        return chunks
