"""Collection and Document managers.

These classes provide the **business-logic** layer that the API routes
consume.  Collection metadata (name, owner, etc.) lives in Postgres
(langchain_pg_collection).  All embedding / chunk data lives in Milvus.
"""

from __future__ import annotations

import builtins
import json
import logging
from typing import Any, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from langchain_core.documents import Document

from langconnect.database.connection import get_vectorstore
from langconnect.database.postgres.repositories.collection_repo import (
    CollectionRepository,
)
from langconnect.models.collection import CollectionDetails

logger = logging.getLogger(__name__)
MILVUS_QUERY_BATCH_SIZE = 10_000


def _parse_milvus_meta(raw: Any) -> dict[str, Any]:
    """Coerce whatever Milvus hands back for the metadata field into a plain dict."""
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


class CollectionsManager:
    """Use to create, delete, update, and list document collections."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self._repo = CollectionRepository(user_id)

    @staticmethod
    async def setup() -> None:
        """Run any necessary initialisation (vectorstore bootstrap)."""
        logger.info("Starting vector store initialization...")
        from langconnect import config

        if config.VECTOR_DB_PROVIDER.lower() != "pgvector":
            logger.info(
                "Vector DB provider: %s — skipping PGVector table bootstrap.",
                config.VECTOR_DB_PROVIDER,
            )
        else:
            get_vectorstore()
        logger.info("Vector store initialization complete.")

    async def list(self) -> list[CollectionDetails]:
        """List all collections owned by the given user."""
        return await self._repo.list_collections()

    async def get(self, collection_id: str) -> CollectionDetails | None:
        """Fetch a single collection by UUID, ensuring the user owns it."""
        return await self._repo.get_collection(collection_id)

    async def create(
        self,
        collection_name: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails | None:
        """Create a new collection."""
        return await self._repo.create_collection(collection_name, metadata)

    async def update(
        self,
        collection_id: str,
        *,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails:
        """Update collection metadata / name."""
        if metadata is None and name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must update at least 1 attribute.",
            )

        result = await self._repo.update_collection(
            collection_id, name=name, metadata=metadata
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{collection_id}' not found or not owned by you.",
            )
        return result

    async def delete(self, collection_id: str) -> int:
        """Delete a collection by UUID.  Returns rows deleted."""
        return await self._repo.delete_collection(collection_id)


class Collection:
    """A collection of documents.

    Collection metadata is kept in Postgres (langchain_pg_collection).
    All chunk / embedding data is stored and queried from Milvus.
    """

    def __init__(self, collection_id: str, user_id: str) -> None:
        self.collection_id = collection_id
        self.user_id = user_id
        self._col_repo = CollectionRepository(user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_details_or_raise(self) -> dict[str, Any]:
        """Return collection metadata from Postgres; raise 404 if missing."""
        details = await self._col_repo.get_collection(self.collection_id)
        if not details:
            raise HTTPException(status_code=404, detail="Collection not found")
        return details

    def _get_store(self, table_id: str):
        """Return the Milvus vector store for the given table_id."""
        return get_vectorstore(collection_name=table_id)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert(self, documents: list[Document]) -> list[str]:
        """Embed and store documents in Milvus."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        ids = store.add_documents(documents)
        return [str(i) for i in ids]

    async def delete(self, *, file_id: Optional[str] = None) -> bool:
        """Delete all chunks with the given file_id from Milvus."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        try:
            store.delete(expr=f'{store._metadata_field}["file_id"] == "{file_id}"')
            logger.info(
                "Deleted Milvus chunks for file %r in collection %r.",
                file_id,
                self.collection_id,
            )
        except Exception as exc:
            logger.warning("Milvus delete failed for file %r: %s", file_id, exc)
        return True

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list(self, *, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """List one representative chunk per unique file_id in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return []

        try:
            rows = store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
                limit=10_000,
            )
        except Exception as exc:
            logger.warning(
                "Milvus query failed for collection %r: %s", self.collection_id, exc
            )
            return []

        # Deduplicate: one representative chunk per file_id
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            meta = _parse_milvus_meta(row.get(store._metadata_field))
            fid = meta.get("file_id") or str(row.get(store._primary_field, ""))
            if fid not in seen:
                seen[fid] = {
                    "id": fid,
                    "content": row.get(store._text_field, ""),
                    "metadata": meta,
                    "collection_id": self.collection_id,
                }

        all_docs = list(seen.values())
        return all_docs[offset : offset + limit]

    async def count(self) -> int:
        """Return the number of distinct documents (unique file_ids) in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return 0

        try:
            rows = store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._metadata_field],
                limit=10_000,
            )
        except Exception:
            return 0

        file_ids = {
            _parse_milvus_meta(r.get(store._metadata_field)).get("file_id", str(i))
            for i, r in enumerate(rows)
        }
        return len(file_ids)

    async def get(self, document_id: str) -> dict[str, Any]:
        """Fetch one chunk for a given file_id."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        try:
            rows = store.col.query(
                expr=f'{store._metadata_field}["file_id"] == "{document_id}"',
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
                limit=1,
            )
        except Exception:
            rows = []

        if not rows:
            raise HTTPException(status_code=404, detail="Document not found")

        row = rows[0]
        return {
            "id": document_id,
            "content": row.get(store._text_field, ""),
            "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
        }

    async def get_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Return all chunks for a given file_id from Milvus."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        try:
            rows = store.col.query(
                expr=f'{store._metadata_field}["file_id"] == "{file_id}"',
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
                limit=10_000,
            )
        except Exception as exc:
            logger.warning("Milvus chunk query failed for file %r: %s", file_id, exc)
            return []

        return [
            {
                "id": str(row.get(store._primary_field, "")),
                "content": row.get(store._text_field, ""),
                "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
            }
            for row in rows
        ]

    async def fetch_all_chunks(self) -> list[dict[str, Any]]:
        """Return every chunk in the collection from Milvus (used by graph build)."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return []

        try:
            rows = self._fetch_milvus_rows(
                store,
                expr=f"{store._primary_field} >= 0",
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
            )
        except Exception as exc:
            logger.warning(
                "Milvus fetch_all_chunks failed for %r: %s", self.collection_id, exc
            )
            return []

        chunks = []
        for row in rows:
            chunks.append(
                {
                    "id": str(row.get(store._primary_field, "")),
                    "content": row.get(store._text_field, ""),
                    "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
                }
            )
        logger.info(
            "Fetched %d chunks from Milvus collection %s",
            len(chunks),
            self.collection_id,
        )
        return chunks

    def _fetch_milvus_rows(
        self,
        store: Any,
        *,
        expr: str,
        output_fields: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch rows without exceeding Milvus' max query result window."""
        if hasattr(store.col, "query_iterator"):
            iterator = store.col.query_iterator(
                expr=expr,
                output_fields=output_fields,
                batch_size=MILVUS_QUERY_BATCH_SIZE,
                limit=-1,
            )
            rows: list[dict[str, Any]] = []
            try:
                while True:
                    batch = iterator.next()
                    if not batch:
                        break
                    rows.extend(batch)
            finally:
                close = getattr(iterator, "close", None)
                if close:
                    close()
            return rows

        return store.col.query(
            expr=expr,
            output_fields=output_fields,
            limit=MILVUS_QUERY_BATCH_SIZE,
        )

    async def search(
        self, query: str, *, limit: int = 4
    ) -> builtins.list[dict[str, Any]]:
        """Run a semantic similarity search in the vector store."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        results = store.similarity_search_with_score(query, k=limit)
        return [
            {
                "id": doc.id or (doc.metadata.get("file_id") if doc.metadata else None),
                "page_content": doc.page_content,
                "metadata": doc.metadata or {},
                "score": score,
            }
            for doc, score in results
        ]
