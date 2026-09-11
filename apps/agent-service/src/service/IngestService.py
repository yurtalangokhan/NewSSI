"""Ingestion service.

Handles Airbyte batch ingestion, document conversion, vector storage, and source preview.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agents.tools import load_vector_store
from core.db import DatasourceRepository
from core.logger import get_logger
from models.ingest import BatchRequest, BatchResponse, SourcePreviewRequest
from repository.airbyte_mapping_repository import AirbyteMappingDB
from service.AirbyteApiClientService import get_airbyte_client

logger = get_logger(__name__)


class IngestService:
    """Service layer for document ingestion and source preview."""

    def __init__(self) -> None:
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )

    @staticmethod
    def _sanitize_metadata_value(value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, Decimal)):
            return value.isoformat()
        if isinstance(value, (list, tuple)):
            return [IngestService._sanitize_metadata_value(v) for v in value]
        if isinstance(value, dict):
            return {k: IngestService._sanitize_metadata_value(v) for k, v in value.items()}
        try:
            return str(value)
        except Exception:
            return None

    def _records_to_documents(
        self,
        records: list[dict[str, Any]],
        stream_name: str,
        connector_type: str,
    ) -> list[Document]:
        documents: list[Document] = []
        PRIORITY_FIELDS = ["id", "name", "title", "description", "label"]
        CONTENT_FIELDS = ["content", "body", "text", "message", "value"]
        EXCLUDE_FIELDS = {"id", "uuid", "_ab_cdc_cursor"}

        for record in records:
            if not record or not isinstance(record, dict):
                continue

            content_parts: list[str] = []
            for field in PRIORITY_FIELDS:
                if field in record and record[field]:
                    content_parts.append(f"{field}: {record[field]}")
            for field in CONTENT_FIELDS:
                if field in record and record[field]:
                    content_parts.append(str(record[field]))
            if not content_parts:
                content_parts = [
                    f"{k}: {v}"
                    for k, v in record.items()
                    if v is not None and not k.startswith("_") and k.lower() not in EXCLUDE_FIELDS
                ]

            content = "\n".join(content_parts).strip()
            if not content:
                continue

            metadata: dict[str, Any] = {
                "source": f"airbyte:{connector_type}",
                "stream": stream_name,
                "connector_type": connector_type,
            }
            for key, value in record.items():
                if value is not None and not key.startswith("_"):
                    metadata[key] = self._sanitize_metadata_value(value)

            documents.append(Document(page_content=content, metadata=metadata))

        return documents

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        words = len(text.split())
        return max(words, int(len(text) / 4))

    async def _update_chunk_stats(
        self,
        datasource_id: str,
        batch_index: int,
        chunk_char_total: int,
        chunk_token_total: int,
        chunk_count: int,
    ) -> None:
        """Update rolling chunk stats in datasource metadata for UI counters."""
        ds_repo = DatasourceRepository()
        row = await ds_repo.get_collection(datasource_id)
        if not row:
            return

        meta = row.get("cmetadata", {}) or {}
        stats = meta.get("chunk_stats", {}) or {}

        if batch_index == 0:
            total_chunks = 0
            total_chars = 0
            total_tokens = 0
        else:
            total_chunks = int(stats.get("chunk_count", 0) or 0)
            total_chars = int(stats.get("_total_chunk_chars", 0) or 0)
            total_tokens = int(stats.get("_total_chunk_tokens", 0) or 0)

        total_chunks += chunk_count
        total_chars += chunk_char_total
        total_tokens += chunk_token_total

        avg_chars = int(total_chars / total_chunks) if total_chunks else 0
        avg_tokens = int(total_tokens / total_chunks) if total_chunks else 0

        meta["chunk_stats"] = {
            "chunk_count": total_chunks,
            "avg_chunk_chars": avg_chars,
            "avg_chunk_tokens": avg_tokens,
            "_total_chunk_chars": total_chars,
            "_total_chunk_tokens": total_tokens,
        }
        await ds_repo.update_collection_metadata(datasource_id, meta)

    async def ingest_batch(self, req: BatchRequest) -> BatchResponse:
        datasource_id = req.datasource_id
        row = await DatasourceRepository().get_collection(datasource_id)
        if not row:
            raise LookupError(f"Datasource {datasource_id} not found")

        collection_name = row.get("name")
        connector_type = req.connector_type or row.get("cmetadata", {}).get(
            "connector_type", "unknown"
        )
        records = req.records or []

        if not records:
            return BatchResponse(
                status="empty",
                batch_index=req.batch_index,
                records_received=0,
                chunks_indexed=0,
                datasource_id=datasource_id,
                is_last_batch=req.is_last_batch,
                error=None,
            )

        docs = self._records_to_documents(records, req.stream_name, connector_type)
        if not docs:
            return BatchResponse(
                status="empty",
                batch_index=req.batch_index,
                records_received=len(records),
                chunks_indexed=0,
                datasource_id=datasource_id,
                is_last_batch=req.is_last_batch,
                error=None,
            )

        vector_store = load_vector_store(collection_name)
        if not vector_store:
            raise RuntimeError(f"Could not load vector store for {collection_name}")

        # Clear all existing chunks on the first batch of a new sync so that
        # re-syncs don't accumulate duplicate entries in Milvus.
        if req.batch_index == 0 and vector_store.col is not None:
            try:
                await asyncio.to_thread(
                    vector_store.col.delete, f"{vector_store._primary_field} >= 0"
                )
                logger.info(
                    "Cleared existing Milvus chunks for datasource %s before re-sync", datasource_id
                )
            except Exception as exc:
                logger.warning("Failed to clear Milvus chunks for %s: %s", datasource_id, exc)

        chunks = self._text_splitter.split_documents(docs)
        if chunks:
            await asyncio.to_thread(vector_store.add_documents, chunks)
            chunk_char_total = 0
            chunk_token_total = 0
            for chunk in chunks:
                text = chunk.page_content or ""
                chunk_char_total += len(text)
                chunk_token_total += self._estimate_token_count(text)
            tokens = chunk_token_total
            await self._update_chunk_stats(
                datasource_id=datasource_id,
                batch_index=req.batch_index,
                chunk_char_total=chunk_char_total,
                chunk_token_total=chunk_token_total,
                chunk_count=len(chunks),
            )
        else:
            tokens = 0

        logger.info(
            "Ingested batch %s: %d records → %d docs → %d chunks",
            req.batch_id,
            len(records),
            len(docs),
            len(chunks),
        )

        return BatchResponse(
            status="success",
            batch_index=req.batch_index,
            records_received=len(records),
            chunks_indexed=len(chunks),
            datasource_id=datasource_id,
            is_last_batch=req.is_last_batch,
            tokens_embedded=tokens,
            error=None,
        )

    async def source_preview(self, req: SourcePreviewRequest) -> dict[str, Any]:
        row = await DatasourceRepository().get_collection(req.datasource_id)
        if not row:
            raise LookupError("Datasource not found")

        mapping = await AirbyteMappingDB.get(req.datasource_id)
        if not mapping:
            raise LookupError("No Airbyte mapping found")

        client = get_airbyte_client()
        source_id = mapping["airbyte_source_id"]

        schema = await client.discover_source_schema(source_id)
        catalog = schema.get("catalog", {})
        streams = catalog.get("streams", [])

        stream_info = []
        for stream in streams:
            stream_def = stream.get("stream", {})
            json_schema = stream_def.get("json_schema", {}) or stream_def.get("jsonSchema", {})
            properties = json_schema.get("properties", {}) if isinstance(json_schema, dict) else {}
            stream_info.append(
                {
                    "name": stream_def.get("name", ""),
                    "key_properties": stream_def.get("key_properties", []),
                    "field_count": len(properties),
                    "schema": json_schema,
                }
            )

        return {
            "datasource_id": req.datasource_id,
            "source_name": row.get("name", ""),
            "connector_type": row.get("cmetadata", {}).get("connector_type", "unknown"),
            "streams": stream_info,
            "note": "This is live schema from the source. Actual data is only stored as embeddings.",
        }

    async def update_progress(self, datasource_id: str, stage: str, progress: int) -> None:
        ds_repo = DatasourceRepository()
        row = await ds_repo.get_collection(datasource_id)
        if not row:
            return

        meta = row.get("cmetadata", {})
        meta["sync_status"] = stage
        meta["sync_progress"] = progress
        await ds_repo.update_collection_metadata(datasource_id, meta)

    async def finalize_sync(self, datasource_id: str) -> None:
        ds_repo = DatasourceRepository()
        row = await ds_repo.get_collection(datasource_id)
        if not row:
            return

        meta = row.get("cmetadata", {})
        meta["sync_status"] = "idle"
        meta["sync_progress"] = 100
        await ds_repo.update_collection_metadata(datasource_id, meta)
        logger.info("Finalized sync for datasource %s", datasource_id)
