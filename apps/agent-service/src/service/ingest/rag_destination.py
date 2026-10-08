"""In-process connector destination that feeds a datasource's RAG collection.

The sync runner hands this destination one batch of source records at a time.
Each batch is turned into plain text + metadata and sent to rag-service, which
owns chunking, embedding and the vector store (see
``integrations.rag_client.ingest_datasource_records``). Nothing is written to
disk and at most one batch is in memory.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
import hashlib
from http import HTTPStatus
import json
from typing import Any, ClassVar
from uuid import uuid4

from connector import (
    BaseDestination,
    Batch,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    DestinationSyncMode,
    DestinationWriteError,
    WriteResult,
)
from error_contract import ApplicationError
from pydantic import BaseModel

from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import datasource_repository
from integrations.rag_client import ingest_datasource_records, retire_datasource_runs
from service.ingest.connector_stores import RAG_DESTINATION

logger = get_logger(__name__)

_PRIORITY_FIELDS = ("id", "name", "title", "description", "label")
_CONTENT_FIELDS = ("content", "body", "text", "message", "value")
_EXCLUDE_FIELDS = frozenset({"id", "uuid"})
#: Bounds of the metadata sent with a document: one value, and the whole, as JSON
#: characters. Milvus stores a chunk's metadata as one JSON field of at most 64 KiB.
_METADATA_VALUE_LIMIT = 4_096
_METADATA_TOTAL_LIMIT = 32_768
#: Chunk metadata naming the sync run that wrote the record. An ``overwrite`` sync
#: retires every chunk of the collection that does not carry its own job id once
#: it is complete (rag-service ``POST /datasources/{id}/records/retire``).
SYNC_JOB_METADATA_KEY = "_sync_job_id"


def sanitize_metadata_value(value: Any) -> Any:
    """Reduce a record value to something JSON and the vector store accept."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [sanitize_metadata_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): sanitize_metadata_value(v) for k, v in value.items()}
    return str(value)


def _bounded_metadata(base: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """The record's fields as chunk metadata, within what Milvus stores per chunk.

    rag-service copies the metadata onto every chunk, and Milvus keeps it as one
    JSON field of at most 64 KiB. The text fields are the document's content and
    stay out; a long value is cut to :data:`_METADATA_VALUE_LIMIT` characters (a
    nested one over it is dropped); fields are added while the whole stays under
    :data:`_METADATA_TOTAL_LIMIT`. The base fields always fit.
    """
    metadata = dict(base)
    size = len(json.dumps(metadata, ensure_ascii=False))
    for key, value in record.items():
        if value is None or key.startswith("_") or key.lower() in _CONTENT_FIELDS:
            continue
        clean = sanitize_metadata_value(value)
        encoded = json.dumps(clean, ensure_ascii=False)
        if len(encoded) > _METADATA_VALUE_LIMIT:
            if not isinstance(clean, str):
                continue
            clean = clean[:_METADATA_VALUE_LIMIT]
            encoded = json.dumps(clean, ensure_ascii=False)
        entry = len(encoded) + len(json.dumps(key, ensure_ascii=False)) + 2  # ``"key": value, ``
        if size + entry > _METADATA_TOTAL_LIMIT:
            continue
        metadata[key] = clean
        size += entry
    return metadata


def _primary_key_values(record: dict[str, Any], primary_key: Sequence[Sequence[str]]) -> list[Any] | None:
    """The record's value for every field path of ``primary_key``, or ``None`` when one is missing."""
    values: list[Any] = []
    for path in primary_key:
        value: Any = record if path else None
        for field in path:
            value = value.get(field) if isinstance(value, dict) else None
        if value is None:
            return None
        values.append(value)
    return values


def record_key(
    stream_name: str,
    record: dict[str, Any],
    primary_key: Sequence[Sequence[str]] | None = None,
) -> str:
    """Name a record for rag-service, which keeps one version per key (a SHA-1 in hex).

    The key is made of the primary-key values when the stream has a primary key
    and the record a value for each of its fields: a changed record then
    replaces its earlier version. Otherwise it is made of the whole record,
    which replaces itself only when it comes again unchanged.
    """
    identity: Any = _primary_key_values(record, primary_key) if primary_key else None
    if identity is None:
        identity = record
    canonical = json.dumps(sanitize_metadata_value(identity), sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(f"{stream_name}\0{canonical}".encode(), usedforsecurity=False).hexdigest()


def records_to_documents(
    records: list[dict[str, Any]],
    stream_name: str,
    connector_type: str,
    primary_key: Sequence[Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Turn source records into ``{"content", "metadata", "record_key"}`` documents.

    Well-known identifying and text fields come first; a record with neither is
    rendered as ``key: value`` lines so no row is silently dropped.
    """
    documents: list[dict[str, Any]] = []
    for record in records:
        if not record or not isinstance(record, dict):
            continue

        parts = [f"{field}: {record[field]}" for field in _PRIORITY_FIELDS if record.get(field)]
        parts.extend(str(record[field]) for field in _CONTENT_FIELDS if record.get(field))
        if not parts:
            parts = [
                f"{key}: {value}"
                for key, value in record.items()
                if value is not None and not key.startswith("_") and key.lower() not in _EXCLUDE_FIELDS
            ]

        content = "\n".join(parts).strip()
        if not content:
            continue

        metadata = _bounded_metadata(
            {"source": f"connector:{connector_type}", "stream": stream_name, "connector_type": connector_type},
            record,
        )
        documents.append(
            {
                "content": content,
                "metadata": metadata,
                "record_key": record_key(stream_name, record, primary_key),
            }
        )
    return documents


def _key_reused(exc: Exception) -> bool:
    """Did rag-service answer ``409 idempotency_key_reused``?

    ``rag_client`` raises an enveloped answer as :class:`ApplicationError` with
    rag-service's status and code (never an ``httpx`` exception). The status
    alone does not tell: a request still in progress is a 409 too, and that one
    is worth retrying.
    """
    return (
        isinstance(exc, ApplicationError)
        and exc.status_code == HTTPStatus.CONFLICT
        and exc.code == "idempotency_key_reused"
    )


def _describe(exc: Exception) -> str:
    """A failed write as the job's reason: rag-service's status and code when it answered."""
    if isinstance(exc, ApplicationError):
        return f"HTTP {exc.status_code} {exc.code}: {exc}"
    return f"{type(exc).__name__}: {exc}"


class RagDatasourceConfig(BaseModel):
    datasource_id: str
    connector_type: str = "unknown"


class RagDatasourceDestination(BaseDestination[RagDatasourceConfig]):
    """Writes batches into the rag-service collection of one datasource."""

    definition: ClassVar[ConnectorDefinition] = ConnectorDefinition(
        name=RAG_DESTINATION,
        display_name="RAG datasource",
        kind=ConnectorKind.DESTINATION,
        category=ConnectorCategory.VECTOR_STORE,
    )
    Config = RagDatasourceConfig

    def __init__(self, config: RagDatasourceConfig) -> None:
        super().__init__(config)
        # One destination instance serves one sync run. rag-service requires an
        # idempotency key per write; scoping it to the run lets a batch whose
        # answer was lost replay instead of double-indexing, without ever matching
        # the same stream/batch position of an earlier sync. ``begin`` replaces this
        # with the id of the sync job, which is what the run is called everywhere else.
        self._run_id = uuid4().hex
        #: ``(key, error)`` of the batch whose write last failed, until it succeeds.
        self._failed_write: tuple[str, Exception] | None = None
        #: Primary key (field paths) per stream, kept by ``begin``; names the records.
        self._primary_keys: dict[str, list[list[str]]] = {}
        #: Destination modes of the run's streams, kept by ``begin`` for ``finalize``.
        self._modes: set[DestinationSyncMode] = set()

    def _idempotency_key(self, *parts: str | int) -> str:
        """A key for one write of this run, in the alphabet rag-service accepts.

        Its middleware answers 400 to anything but letters, digits, ``.``, ``_``
        and ``-`` (at most 255 of them), so the parts are joined with dots.
        """
        return ".".join(("connector-sync", self.config.datasource_id, self._run_id, *map(str, parts)))

    def _batch_key(self, batch: Batch) -> str:
        # A stream is named by its source: spaces, slashes, any script, any length.
        # Its digest is what a key can carry.
        stream = hashlib.sha1(batch.stream.encode(), usedforsecurity=False).hexdigest()[:16]
        return self._idempotency_key(stream, batch.batch_index)

    async def check(self) -> CheckResult:
        row = await datasource_repository().get_collection(self.config.datasource_id)
        if row is None:
            return CheckResult(ok=False, message=f"datasource {self.config.datasource_id} not found")
        return CheckResult(ok=True)

    async def begin(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,  # noqa: ARG002
        *,
        job_id: str | None = None,
    ) -> None:
        """Keep the primary keys and destination modes of the streams.

        An ``overwrite`` sync clears nothing here: its records land next to the
        previous version, which stays searchable until :meth:`finalize` retires it.
        A run that fails leaves the previous version in place.
        """
        if job_id:
            self._run_id = job_id
        self._primary_keys = {
            configured.stream.name: configured.primary_key or configured.stream.source_defined_primary_key
            for configured in catalog.streams
        }
        self._modes = {configured.destination_sync_mode for configured in catalog.streams}

    async def finalize(
        self,
        catalog: ConfiguredCatalog,  # noqa: ARG002
        connection_id: str | None = None,  # noqa: ARG002
        *,
        job_id: str | None = None,  # noqa: ARG002
    ) -> None:
        """Retire every chunk this run did not write, when every stream overwrites.

        Stream names are free text and cannot scope a Milvus filter, so a catalog
        that mixes modes is left as it is: a retire would take the ``append``
        streams' history with it. The chunk statistics lose what the retire removed.
        """
        if DestinationSyncMode.OVERWRITE not in self._modes:
            return
        if self._modes != {DestinationSyncMode.OVERWRITE}:
            logger.warning(
                "Datasource %s mixes overwrite and append streams: the previous version is kept",
                self.config.datasource_id,
            )
            return
        result = await retire_datasource_runs(
            self.config.datasource_id,
            keep_job_id=self._run_id,
            idempotency_key=self._idempotency_key("retire"),
            access_token=None,
        )
        removed = int(result.get("chunks_removed", 0) or 0)
        if removed:
            await self._add_chunk_stats(chunk_count=0, chunk_chars=0, chunk_tokens=0, chunks_replaced=removed)
        logger.info("Retired %d chunks of earlier runs of datasource %s", removed, self.config.datasource_id)

    async def write(self, batch: Batch) -> WriteResult:
        documents = records_to_documents(
            [record.data for record in batch.records],
            batch.stream,
            self.config.connector_type,
            primary_key=self._primary_keys.get(batch.stream),
        )
        if not documents:
            return WriteResult(records_written=0)
        for document in documents:
            document["metadata"][SYNC_JOB_METADATA_KEY] = self._run_id

        result = await self._ingest(batch, documents)
        chunks_indexed = int(result.get("chunks_indexed", 0))
        chunks_replaced = int(result.get("chunks_replaced", 0) or 0)
        if chunks_indexed or chunks_replaced:
            await self._add_chunk_stats(
                chunk_count=chunks_indexed,
                chunk_chars=int(result.get("chunk_char_total", 0)),
                chunk_tokens=int(result.get("chunk_token_total", 0)),
                chunks_replaced=chunks_replaced,
            )
        logger.info(
            "Ingested %s batch %d of datasource %s: %d records -> %d docs -> %d chunks (%d replaced)",
            batch.stream,
            batch.batch_index,
            self.config.datasource_id,
            batch.size,
            len(documents),
            chunks_indexed,
            chunks_replaced,
        )
        return WriteResult(records_written=len(documents), extra={"chunks_indexed": chunks_indexed})

    async def _ingest(self, batch: Batch, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """Send one batch; a retry rag-service refuses ends with the first failure as its reason.

        rag-service frees the key of a write that failed with 429 / 5xx, so the
        runner's retry runs it again, and the record keys make that safe. A
        write it refused for another reason keeps its key: every retry is
        answered ``409 idempotency_key_reused``, trying again cannot help, and
        that answer says nothing about what went wrong.
        """
        key = self._batch_key(batch)
        try:
            # No user token: a sync outlives the request that started it, and a
            # scheduled one never had a user. rag-service is called as a service.
            result = await ingest_datasource_records(
                self.config.datasource_id,
                documents,
                clear_existing=False,
                idempotency_key=key,
                access_token=None,
            )
        except Exception as exc:
            first = self._failed_write[1] if self._failed_write and self._failed_write[0] == key else None
            if _key_reused(exc):
                reason = (
                    f"the first attempt failed with {_describe(first)}"
                    if first is not None
                    else "an earlier attempt used its idempotency key"
                )
                raise DestinationWriteError(
                    f"rag-service will not run batch {batch.batch_index} of stream '{batch.stream}' again; {reason}"
                ) from (first or exc)
            if first is None:
                self._failed_write = (key, exc)
            raise
        self._failed_write = None
        return result

    # ---- chunk statistics shown by the datasource UI --------------------

    async def _add_chunk_stats(
        self, *, chunk_count: int, chunk_chars: int, chunk_tokens: int, chunks_replaced: int = 0
    ) -> None:
        """Add what one write stored, after taking out the chunks it replaced.

        The sizes of replaced chunks are not known any more, so they leave at the
        current average. Never more of them than the statistics hold: a write
        rag-service stored and then failed was not counted here, and its retry
        reports those chunks as replaced.
        """
        repo = datasource_repository()
        row = await repo.get_collection(self.config.datasource_id)
        if not row:
            return

        meta = row.get("cmetadata", {}) or {}
        stats = meta.get("chunk_stats", {}) or {}
        stored_chunks = int(stats.get("chunk_count", 0) or 0)
        stored_chars = int(stats.get("_total_chunk_chars", 0) or 0)
        stored_tokens = int(stats.get("_total_chunk_tokens", 0) or 0)
        kept_chunks = max(stored_chunks - chunks_replaced, 0)
        if kept_chunks != stored_chunks:
            stored_chars = stored_chars * kept_chunks // stored_chunks
            stored_tokens = stored_tokens * kept_chunks // stored_chunks
        total_chunks = kept_chunks + chunk_count
        total_chars = stored_chars + chunk_chars
        total_tokens = stored_tokens + chunk_tokens

        meta["chunk_stats"] = {
            "chunk_count": total_chunks,
            "avg_chunk_chars": int(total_chars / total_chunks) if total_chunks else 0,
            "avg_chunk_tokens": int(total_tokens / total_chunks) if total_chunks else 0,
            "_total_chunk_chars": total_chars,
            "_total_chunk_tokens": total_tokens,
        }
        await repo.update_collection_metadata(self.config.datasource_id, meta)
