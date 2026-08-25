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

from error_contract import BadRequestError, NotFoundError
from i18n import t
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
            raise BadRequestError(
                code="collection.update_requires_attribute",
                message=t("collection.update_requires_attribute"),
            )

        result = await self._repo.update_collection(
            collection_id, name=name, metadata=metadata
        )
        if result is None:
            raise NotFoundError(
                code="collection.not_found",
                message=t("collection.not_found_or_not_owned", collection_id=collection_id),
                details={"collection_id": collection_id},
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
            raise NotFoundError(
                code="collection.not_found",
                message=t("collection.not_found"),
                details={"collection_id": self.collection_id},
            )
        return details

    async def ensure_exists(self) -> None:
        """Raise 404 if this collection does not exist / isn't owned by the user."""
        await self._get_details_or_raise()

    def _get_store(self, table_id: str):
        """Return the Milvus vector store for the given table_id."""
        return get_vectorstore(collection_name=table_id)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert(self, documents: list[Document]) -> list[str]:
        """Embed and store documents in Milvus.

        Flushes the collection so a read issued right after this call (e.g.
        the duplicate-filename check in the next upload job) is guaranteed
        to see the rows just inserted here, rather than racing Milvus'
        segment-sealing behavior.
        """
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        ids = store.add_documents(documents)
        if store.col is not None:
            store.col.flush()
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

    async def list_filenames(self) -> set[str]:
        """Return the set of distinct filenames stored in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return set()

        try:
            rows = store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._metadata_field],
                limit=10_000,
            )
        except Exception as exc:
            logger.warning(
                "Milvus filename query failed for collection %r: %s",
                self.collection_id,
                exc,
            )
            return set()

        filenames: set[str] = set()
        for row in rows:
            meta = _parse_milvus_meta(row.get(store._metadata_field))
            filename = meta.get("filename")
            if filename:
                filenames.add(filename)
        return filenames

    async def list_content_hashes(self) -> set[str]:
        """Return the set of distinct content hashes stored in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return set()

        try:
            rows = store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._metadata_field],
                limit=10_000,
            )
        except Exception as exc:
            logger.warning(
                "Milvus content-hash query failed for collection %r: %s",
                self.collection_id,
                exc,
            )
            return set()

        hashes: set[str] = set()
        for row in rows:
            meta = _parse_milvus_meta(row.get(store._metadata_field))
            content_hash = meta.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return hashes

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
            raise NotFoundError(
                code="document.not_found",
                message=t("document.not_found"),
                details={"document_id": document_id, "collection_id": self.collection_id},
            )

        row = rows[0]
        return {
            "id": document_id,
            "content": row.get(store._text_field, ""),
            "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
        }

    async def get_chunks(
        self, file_id: str, *, limit: int = 10_000, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return a page of chunks for a given file_id from Milvus."""
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
                limit=limit,
                offset=offset,
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

    async def get_chunk_stats(self, file_id: str) -> dict[str, int]:
        """Return {total_chunks, avg_chars, avg_tokens} for a file_id.

        Cheap path: chunk stats are precomputed and stored on every chunk's
        metadata at upload time, so a single-row query is enough. Falls back
        to a bounded full scan only for legacy chunks uploaded before those
        fields existed.
        """
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        try:
            rows = store.col.query(
                expr=f'{store._metadata_field}["file_id"] == "{file_id}"',
                output_fields=[store._text_field, store._metadata_field],
                limit=1,
            )
        except Exception as exc:
            logger.warning(
                "Milvus chunk-stats query failed for file %r: %s", file_id, exc
            )
            return {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}

        if not rows:
            return {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}

        meta = _parse_milvus_meta(rows[0].get(store._metadata_field))
        total_chunks = meta.get("file_total_chunks", 0)
        if total_chunks:
            return {
                "total_chunks": total_chunks,
                "avg_chars": meta.get("file_avg_chars", 0),
                "avg_tokens": meta.get("file_avg_tokens", 0),
            }

        # Legacy fallback: recompute from a full (bounded) scan.
        all_rows = store.col.query(
            expr=f'{store._metadata_field}["file_id"] == "{file_id}"',
            output_fields=[store._text_field, store._metadata_field],
            limit=10_000,
        )
        total = len(all_rows)
        if total == 0:
            return {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}
        total_chars = sum(len(r.get(store._text_field, "")) for r in all_rows)
        total_tokens = sum(
            _parse_milvus_meta(r.get(store._metadata_field)).get(
                "token_count", len(r.get(store._text_field, "")) // 4
            )
            for r in all_rows
        )
        return {
            "total_chunks": total,
            "avg_chars": round(total_chars / total),
            "avg_tokens": round(total_tokens / total),
        }

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
