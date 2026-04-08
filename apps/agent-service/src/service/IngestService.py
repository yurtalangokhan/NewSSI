"""Ingestion service.

Handles Airbyte batch ingestion, document conversion, vector storage, and source preview.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from agents.tools import load_vector_store
from core.db import AirbyteMappingRepository, DatasourceRepository
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from service.AirbyteApiClientService import get_airbyte_client
from service.AirbyteMappingRepository import AirbyteMappingDB
from service.Schemas import BatchRequest, BatchResponse, SourcePreviewRequest

logger = logging.getLogger(__name__)


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

    async def ingest_batch(self, req: BatchRequest) -> BatchResponse:
        datasource_id = req.datasource_id
        row = await DatasourceRepository().get_collection(datasource_id)
        if not row:
            raise LookupError(f"Datasource {datasource_id} not found")

        collection_name = row.get("name")
        connector_type = req.connector_type or row.get("cmetadata", {}).get("connector_type", "unknown")
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

        chunks = self._text_splitter.split_documents(docs)
        if chunks:
            await asyncio.to_thread(vector_store.add_documents, chunks)
            tokens = sum(self._estimate_token_count(chunk.page_content or "") for chunk in chunks)
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
