# Copyright (c) 2026 Agentic AI Platform
"""Per-collection Milvus chunk/embedding operations.

``Collection`` is the only thing in this service that opens a Milvus
connection or embeds text — every read, write, search, stats, and
dedup-fingerprint lookup against chunk data goes through it. Collection
*metadata* (name, owner, connector type) lives in Postgres and is
``collections.service.CollectionsManager``'s job, not this
module's; ``Collection`` only reads that metadata (via
``CollectionsManager``) to resolve which Milvus table it should talk to.
"""

from __future__ import annotations

import asyncio
import builtins
import json
from typing import Any
import weakref

from error_contract import CollectionNotFoundError, DependencyUnavailableError, NotFoundError
from langchain_core.documents import Document
from localization import t

from src.collections.service import CollectionsManager
from src.shared.errors import database_errors
from src.shared.milvus_expr import (
    metadata_equals,
    metadata_in,
    metadata_missing_or_not_equals,
    metadata_path,
)
from src.shared.observability import get_logger
from src.shared.vectorstore import forget_vectorstore, get_vectorstore

logger = get_logger(__name__)
MILVUS_QUERY_BATCH_SIZE = 10_000
#: Terms in one ``in [...]`` filter. A filter is a string the server parses,
#: so a long list of record keys or primary keys is sent a slice at a time.
MILVUS_TERM_BATCH_SIZE = 500
#: Metadata key that names the source record a connector-managed chunk was
#: cut from. Set by the records route, matched by ``replace_records``.
RECORD_KEY_METADATA_KEY = "_record_key"
#: Metadata key naming the sync run that wrote a connector-managed chunk. Set
#: by agent-service on every document; ``retire_other_runs`` keeps one run.
SYNC_JOB_METADATA_KEY = "_sync_job_id"
#: Milvus index on that key's JSON path. ``replace_records`` looks chunks up
#: by record key once per batch; without the index that lookup reads the
#: metadata of every chunk in the collection.
RECORD_KEY_INDEX_NAME = "record_key"
#: Stores whose collection was asked for that index, so that a collection is
#: asked once per cached store and not once per batch. Held weakly: a store
#: the vector-store cache drops is forgotten here as well.
_RECORD_KEY_INDEXED_STORES: weakref.WeakSet[Any] = weakref.WeakSet()


def _parse_milvus_meta(raw: Any) -> dict[str, Any]:
    """Coerce whatever Milvus hands back for the metadata field into a plain dict."""
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


class Collection:
    """A collection of documents.

    Collection metadata is kept in Postgres (langchain_pg_collection).
    All chunk / embedding data is stored and queried from Milvus.
    """

    def __init__(self, collection_id: str, user_id: str) -> None:
        self.collection_id = collection_id
        self.user_id = user_id

    async def _get_details_or_raise(self, required_permission: str = "read") -> dict[str, Any]:
        """Return collection metadata from Postgres; raise 404 if missing."""
        details = await CollectionsManager(self.user_id).get(self.collection_id, required_permission)
        if not details:
            raise CollectionNotFoundError(
                details={"collection_id": self.collection_id},
            )
        return details

    async def ensure_exists(self, required_permission: str = "read") -> None:
        """Raise 404 when the collection is missing or inaccessible."""
        await self._get_details_or_raise(required_permission)

    def _get_store(self, table_id: str):
        """Return the Milvus vector store for the given table_id."""
        with database_errors():
            return get_vectorstore(collection_name=table_id)

    @staticmethod
    async def _query(store: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Run a Milvus collection query off the event loop (spec T5): pymilvus's
        Collection.query is synchronous and was previously called inline,
        stalling every other request for however long the query took.
        """
        return await asyncio.to_thread(store.col.query, **kwargs)

    async def upsert(self, documents: list[Document]) -> list[str]:
        """Embed and store documents in Milvus.

        A read issued right after this call (e.g. the duplicate-filename
        check in the next upload job) needs to see the rows just inserted
        here. That used to be guaranteed by flush()ing on every write, which
        forces a segment seal and pays that cost unconditionally -- even
        when nothing reads the collection again soon after. Milvus documents
        consistency_level="Strong" as the read-side mechanism for exactly
        this "see all completed writes" requirement, so _fetch_milvus_rows
        requests it instead.
        """
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        with database_errors():
            # add_documents embeds every document and writes to Milvus
            # synchronously, which ran inline on the event loop, stalling every
            # other request (including health checks) for as long as
            # embedding+write took (spec T5).
            ids = await asyncio.to_thread(store.add_documents, documents)
        return [str(i) for i in ids]

    async def delete(self, *, file_id: str | None = None) -> None:
        """Delete all chunks with the given file_id from Milvus."""
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        with database_errors():
            await asyncio.to_thread(
                store.delete,
                expr=metadata_equals(store._metadata_field, "file_id", file_id),
            )

        logger.info(
            "Deleted Milvus chunks for file %r in collection %r.",
            file_id,
            self.collection_id,
        )

    async def clear(self) -> int:
        """Delete every chunk in this collection from Milvus. Returns the count removed.

        Used by connector-managed (datasource) ingestion before re-indexing on
        a resync, so re-syncs don't accumulate duplicate entries -- there is
        no per-record file_id to scope a targeted :meth:`delete` by.
        """
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        if store.col is None:
            return 0
        with database_errors():
            count_before = await asyncio.to_thread(lambda: int(store.col.num_entities or 0))
            # Safe: store._primary_field is the vectorstore's own primary-key
            # field name, never caller-supplied.
            await asyncio.to_thread(store.col.delete, f"{store._primary_field} >= 0")
        logger.info(
            "Cleared %d Milvus entities for collection %r.",
            count_before,
            self.collection_id,
        )
        return count_before

    async def drop(self) -> int:
        """Drop this collection's Milvus table. Returns the number of chunks it held.

        The end of a datasource: agent-service calls this before it deletes the
        collection row that names the table, after which nothing could reach the
        chunks any more. A collection that was never written to has no table and
        nothing to drop; neither has a PGVector store (the legacy provider), which
        keeps no Milvus table. The store cache forgets the collection: a LangChain
        store cannot be reused once its table is gone (its field list would be
        appended to again and the next insert fail on a schema mismatch), so a
        later write builds a fresh store and creates the table anew.
        """
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        if getattr(store, "col", None) is None:
            return 0
        with database_errors():
            count_before = await asyncio.to_thread(lambda: int(store.col.num_entities or 0))
            await asyncio.to_thread(store.col.drop)
        store.col = None
        _RECORD_KEY_INDEXED_STORES.discard(store)
        forget_vectorstore(details["table_id"])
        logger.info(
            "Dropped the Milvus table of collection %r (%d entities).",
            self.collection_id,
            count_before,
        )
        return count_before

    async def replace_records(self, record_keys: list[str], documents: list[Document]) -> int:
        """Store ``documents`` and remove what earlier writes stored for ``record_keys``.

        Returns the number of chunks removed. Used by connector-managed
        (datasource) ingestion, where a record that is written again has to
        take the place of its earlier version instead of standing next to it.
        Every chunk of a record carries the record's key in
        ``metadata[RECORD_KEY_METADATA_KEY]``.

        The new chunks are inserted before the old ones are deleted, so a
        failing embedding model removes nothing. When the delete fails, both
        versions are stored and ``DependencyUnavailableError`` (503) tells the
        caller to send the batch again: that run finds both and removes both.

        The index the lookup uses is asked for after the insert: the first
        insert is what creates a new collection in Milvus.
        """
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        stale_ids = await self._find_record_chunk_ids(store, record_keys)
        if documents:
            await asyncio.to_thread(store.add_documents, documents)
        await self._ensure_record_key_index(store)
        await self._delete_chunk_ids(store, stale_ids)
        return len(stale_ids)

    async def retire_other_runs(self, keep_job_id: str) -> int:
        """Remove every chunk that the sync run ``keep_job_id`` did not write.

        The end of an ``overwrite`` sync: the run landed next to the previous
        version of the collection (which stayed searchable meanwhile) and now
        takes its place. Chunks of other runs go, and so do chunks written before
        runs were tagged. Returns the number of chunks removed; a failing Milvus
        call is reported like a failing :meth:`replace_records`.
        """
        details = await self._get_details_or_raise("write")
        store = self._get_store(details["table_id"])
        if store.col is None:
            return 0
        expr = metadata_missing_or_not_equals(store._metadata_field, SYNC_JOB_METADATA_KEY, keep_job_id)
        try:
            rows = await asyncio.to_thread(
                self._fetch_milvus_rows, store, expr=expr, output_fields=[store._primary_field]
            )
        except Exception as exc:
            raise self._replace_failed("lookup", exc) from exc
        stale_ids = [int(row[store._primary_field]) for row in rows]
        await self._delete_chunk_ids(store, stale_ids)
        logger.info(
            "Retired %d chunks of earlier runs in collection %r (kept run %s).",
            len(stale_ids),
            self.collection_id,
            keep_job_id,
        )
        return len(stale_ids)

    async def _find_record_chunk_ids(self, store: Any, record_keys: list[str]) -> list[int]:
        """Return the primary keys of the chunks stored for ``record_keys``.

        The one step of :meth:`replace_records` that depends on how the chunks
        of a record are found. It filters on the metadata JSON, which Milvus
        scans unless that path is indexed: :meth:`_ensure_record_key_index`
        asks for that index.
        """
        if store.col is None:
            return []
        filters = [
            metadata_in(
                store._metadata_field,
                RECORD_KEY_METADATA_KEY,
                record_keys[start : start + MILVUS_TERM_BATCH_SIZE],
            )
            for start in range(0, len(record_keys), MILVUS_TERM_BATCH_SIZE)
        ]
        chunk_ids: list[int] = []
        try:
            for expr in filters:
                rows = await asyncio.to_thread(
                    self._fetch_milvus_rows,
                    store,
                    expr=expr,
                    output_fields=[store._primary_field],
                )
                chunk_ids.extend(int(row[store._primary_field]) for row in rows)
        except Exception as exc:
            raise self._replace_failed("lookup", exc) from exc
        return chunk_ids

    async def _ensure_record_key_index(self, store: Any) -> None:
        """Ask Milvus, once per store, for the index on the record key's JSON path.

        Milvus builds the index in the background (``sync=False``: the write
        does not wait for it) and accepts the request again when the index is
        already there. A request that fails -- a server without JSON path
        indexes, an outage -- leaves the lookup slower, not wrong: it is
        logged and not remembered, so the next write asks again.
        """
        if store.col is None or store in _RECORD_KEY_INDEXED_STORES:
            return
        try:
            index_params = {
                "index_type": "INVERTED",
                "params": {
                    "json_path": metadata_path(store._metadata_field, RECORD_KEY_METADATA_KEY),
                    "json_cast_type": "varchar",
                },
            }
            await asyncio.to_thread(
                store.col.create_index,
                store._metadata_field,
                index_params,
                index_name=RECORD_KEY_INDEX_NAME,
                sync=False,
            )
        except Exception as exc:
            logger.warning(
                "Milvus record-key index request failed for collection %r: %s",
                self.collection_id,
                exc,
            )
        else:
            _RECORD_KEY_INDEXED_STORES.add(store)

    async def _delete_chunk_ids(self, store: Any, chunk_ids: list[int]) -> None:
        """Delete chunks by primary key, a slice at a time."""
        try:
            for start in range(0, len(chunk_ids), MILVUS_TERM_BATCH_SIZE):
                batch = chunk_ids[start : start + MILVUS_TERM_BATCH_SIZE]
                # Safe: the field name is the vectorstore's own and the values
                # are integers read from Milvus, never caller-supplied.
                expr = f"{store._primary_field} in [{', '.join(map(str, batch))}]"
                await asyncio.to_thread(store.col.delete, expr)
        except Exception as exc:
            raise self._replace_failed("delete", exc) from exc

    def _replace_failed(self, stage: str, exc: Exception) -> DependencyUnavailableError:
        """Log a failed Milvus call of :meth:`replace_records` and build its 503."""
        logger.warning(
            "Milvus %s failed while replacing records in collection %r: %s",
            stage,
            self.collection_id,
            exc,
        )
        return DependencyUnavailableError(
            code="datasource.replace_failed",
            message=t("datasource.replace_failed"),
            details={"collection_id": self.collection_id, "stage": stage},
        )

    async def entity_count(self) -> int:
        """Return the raw number of Milvus entities in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        if store.col is None:
            return 0
        with database_errors():
            return await asyncio.to_thread(lambda: int(store.col.num_entities or 0))

    async def list_raw_entities(self, *, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """Return a page of raw rows, unaggregated by file_id."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        if store.col is None:
            return []

        def _query() -> list[dict[str, Any]]:
            return store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._text_field, store._metadata_field],
                limit=limit,
                offset=offset,
            )

        with database_errors():
            rows = await asyncio.to_thread(_query)
        return [
            {
                "content": row.get(store._text_field, ""),
                "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
            }
            for row in rows
        ]

    async def entity_stats(self, *, sample_limit: int = 10_000) -> dict[str, int]:
        """Return approximate chunk and content-size statistics."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        if store.col is None:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}

        def _query() -> list[dict[str, Any]]:
            return store.col.query(
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._text_field],
                limit=sample_limit,
            )

        with database_errors():
            rows = await asyncio.to_thread(_query)
        if not rows:
            return {"chunk_count": 0, "avg_chunk_chars": 0, "avg_chunk_tokens": 0}

        chunk_count = len(rows)
        total_chars = sum(len(row.get(store._text_field, "")) for row in rows)
        avg_chars = total_chars // chunk_count
        return {
            "chunk_count": chunk_count,
            "avg_chunk_chars": avg_chars,
            "avg_chunk_tokens": max(1, avg_chars // 4) if avg_chars else 0,
        }

    async def list(self, *, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """List one representative chunk per unique file_id in this collection.

        Deduplication by file_id needs every row scanned (Milvus has no
        GROUP BY), but only the ``limit`` rows actually returned need their
        text. Scanning with the text field included pulled the collection's
        entire corpus into memory to render one page of ten documents, so
        the scan asks for ids + metadata only and a second, targeted query
        fetches the text for just the page's representative rows.
        """
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return []

        with database_errors():
            # A fixed limit=10_000 silently truncated anything larger and
            # materialised every row at once; the iterator streams in batches.
            rows = await asyncio.to_thread(
                self._fetch_milvus_rows,
                store,
                # Safe: store._primary_field is the vectorstore's own
                # primary-key field name, never caller-supplied.
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._primary_field, store._metadata_field],
            )

        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            meta = _parse_milvus_meta(row.get(store._metadata_field))
            pk = row.get(store._primary_field)
            fid = meta.get("file_id") or str(pk or "")
            if fid not in seen:
                seen[fid] = {
                    "id": fid,
                    "content": "",
                    "metadata": meta,
                    "collection_id": self.collection_id,
                    "_pk": pk,
                }

        page = list(seen.values())[offset : offset + limit]
        await self._attach_text(store, page)
        for doc in page:
            doc.pop("_pk", None)
        return page

    async def _attach_text(self, store: Any, page: list[dict[str, Any]]) -> None:
        """Fill in ``content`` for one page of :meth:`list` results, in place."""
        # Milvus has no query parameter binding, so the primary keys are
        # coerced to int before being embedded in the expression -- they come
        # from Milvus itself and the schema is auto_id int64, so anything that
        # does not coerce means an unexpected schema, not a value to inline.
        pks: list[int] = []
        for doc in page:
            try:
                pks.append(int(doc["_pk"]))
            except (TypeError, ValueError):
                logger.warning(
                    "Non-integer Milvus primary key in collection %r; skipping text fetch for that row.",
                    self.collection_id,
                )
        if not pks:
            return

        with database_errors():
            rows = await self._query(
                store,
                expr=f"{store._primary_field} in [{', '.join(str(pk) for pk in pks)}]",
                output_fields=[store._primary_field, store._text_field],
                limit=len(pks),
            )

        text_by_pk = {str(row.get(store._primary_field)): row.get(store._text_field, "") for row in rows}
        for doc in page:
            doc["content"] = text_by_pk.get(str(doc["_pk"]), "")

    async def list_upload_fingerprints(self) -> tuple[set[str], set[str]]:
        """Return ``(filenames, content_hashes)`` already stored here.

        Both come out of the same field of the same rows, so they are read
        together: as two calls, an upload job streamed the whole collection
        end to end twice before looking at its first file, and that is the
        dominant cost of the job on a collection of any size.

        Storage failures propagate through the shared database error contract.
        """
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return set(), set()

        with database_errors():
            # A fixed limit=10_000 silently truncated anything larger and
            # materialised every row at once; the iterator streams in batches.
            rows = await asyncio.to_thread(
                self._fetch_milvus_rows,
                store,
                # Safe: store._primary_field is the vectorstore's own
                # primary-key field name, never caller-supplied.
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._metadata_field],
            )

        filenames: set[str] = set()
        hashes: set[str] = set()
        for row in rows:
            meta = _parse_milvus_meta(row.get(store._metadata_field))
            filename = meta.get("filename")
            if filename:
                filenames.add(filename)
            content_hash = meta.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return filenames, hashes

    async def count(self) -> int:
        """Return the number of distinct documents (unique file_ids) in this collection."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            return 0

        with database_errors():
            # A fixed limit=10_000 silently truncated anything larger and
            # materialised every row at once; the iterator streams in batches.
            rows = await asyncio.to_thread(
                self._fetch_milvus_rows,
                store,
                # Safe: store._primary_field is the vectorstore's own
                # primary-key field name, never caller-supplied.
                expr=f"{store._primary_field} >= 0",
                output_fields=[store._metadata_field],
            )

        file_ids = {_parse_milvus_meta(r.get(store._metadata_field)).get("file_id", str(i)) for i, r in enumerate(rows)}
        return len(file_ids)

    async def get(self, document_id: str) -> dict[str, Any]:
        """Fetch one chunk for a given file_id."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])

        if store.col is None:
            raise NotFoundError(code="document.not_found", message_key="errors.rag.document.not_found")

        with database_errors():
            rows = await self._query(
                store,
                expr=metadata_equals(store._metadata_field, "file_id", document_id),
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
                limit=1,
            )

        if not rows:
            raise NotFoundError(
                code="document.not_found",
                message_key="errors.rag.document.not_found",
                details={
                    "document_id": document_id,
                    "collection_id": self.collection_id,
                },
            )

        row = rows[0]
        return {
            "id": document_id,
            "content": row.get(store._text_field, ""),
            "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
        }

    async def get_chunks(self, file_id: str, *, limit: int = 10_000, offset: int = 0) -> list[dict[str, Any]]:
        """Return a page of chunks for a given file_id from Milvus."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        if store.col is None:
            return []

        with database_errors():
            rows = await self._query(
                store,
                expr=metadata_equals(store._metadata_field, "file_id", file_id),
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
                limit=limit,
                offset=offset,
            )

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
        if store.col is None:
            return {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}

        with database_errors():
            rows = await self._query(
                store,
                expr=metadata_equals(store._metadata_field, "file_id", file_id),
                output_fields=[store._text_field, store._metadata_field],
                limit=1,
            )

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

        # A fixed limit=10_000 silently truncated anything larger and
        # materialised every row at once; the iterator streams in batches.
        with database_errors():
            all_rows = await asyncio.to_thread(
                self._fetch_milvus_rows,
                store,
                expr=metadata_equals(store._metadata_field, "file_id", file_id),
                output_fields=[store._text_field, store._metadata_field],
            )
        total = len(all_rows)
        if total == 0:
            return {"total_chunks": 0, "avg_chars": 0, "avg_tokens": 0}
        total_chars = sum(len(r.get(store._text_field, "")) for r in all_rows)
        total_tokens = sum(
            _parse_milvus_meta(r.get(store._metadata_field)).get("token_count", len(r.get(store._text_field, "")) // 4)
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

        with database_errors():
            # _fetch_milvus_rows is synchronous end to end (it may loop over
            # a query_iterator until the whole collection is read), so the
            # entire call is offloaded rather than just one query (spec T5).
            rows = await asyncio.to_thread(
                self._fetch_milvus_rows,
                store,
                # Safe: store._primary_field is the vectorstore's own
                # primary-key field name, never caller-supplied.
                expr=f"{store._primary_field} >= 0",
                output_fields=[
                    store._primary_field,
                    store._text_field,
                    store._metadata_field,
                ],
            )

        chunks = [
            {
                "id": str(row.get(store._primary_field, "")),
                "content": row.get(store._text_field, ""),
                "metadata": _parse_milvus_meta(row.get(store._metadata_field)),
            }
            for row in rows
        ]
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
        """Fetch rows without exceeding Milvus' max query result window.

        Requests consistency_level="Strong" so this always sees rows from
        writes that completed before the call, without upsert() having to
        flush() (and pay a segment seal) on every batch it writes.
        """
        if hasattr(store.col, "query_iterator"):
            iterator = store.col.query_iterator(
                expr=expr,
                output_fields=output_fields,
                batch_size=MILVUS_QUERY_BATCH_SIZE,
                limit=-1,
                consistency_level="Strong",
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
            consistency_level="Strong",
        )

    async def search(self, query: str, *, limit: int = 4) -> builtins.list[dict[str, Any]]:
        """Run a semantic similarity search in the vector store."""
        details = await self._get_details_or_raise()
        store = self._get_store(details["table_id"])
        with database_errors():
            # Embeds the query text and queries Milvus synchronously (spec T5).
            results = await asyncio.to_thread(store.similarity_search_with_score, query, k=limit)
        return [
            {
                "id": (doc.metadata or {}).get("file_id") or doc.id,
                "chunk_id": doc.id,
                "page_content": doc.page_content,
                "metadata": doc.metadata or {},
                "score": score,
            }
            for doc, score in results
        ]
