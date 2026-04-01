"""
Batch Ingestion Routes.

HTTP endpoint that receives record batches from the custom Airbyte
``destination-embedding`` connector.  Each batch is immediately:

  1. Converted to LangChain Documents
  2. Split into chunks (RecursiveCharacterTextSplitter)
  3. Embedded (Ollama / OpenAI)
  4. Written to PGVector

**Zero disk I/O** — data flows from source → Airbyte → destination
container → HTTP → embed → PGVector, never touching the filesystem.

Memory model:
  Only one batch (default 200 records) is in RAM at a time.
  After embedding + PGVector write, the batch is released.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agents.tools import load_vector_store
from core.db import AirbyteMappingRepository, DatasourceRepository
from service.schemas import BatchRequest, BatchResponse, SourcePreviewRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


# ============================================================================
# Record → Document conversion (reuses airbyte_connector logic)
# ============================================================================

def _sanitize_metadata_value(value: Any) -> Any:
    """Convert non-JSON-serializable values to safe types."""
    from datetime import date, datetime
    from decimal import Decimal
    if value is None:
        return value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _records_to_documents(
    records: list[dict[str, Any]],
    connector_type: str,
    content_fields: list[str] | None = None,
):
    """Convert raw records to LangChain Documents — same logic as airbyte_connector."""
    from langchain_core.documents import Document

    documents = []
    for record in records:
        stream_name = record.pop("_stream", "unknown")

        if content_fields:
            content_parts = [
                f"{f}: {record[f]}"
                for f in content_fields
                if f in record and record[f]
            ]
            content = "\n".join(content_parts)
        else:
            PRIORITY_FIELDS = ["title", "name", "subject", "heading"]
            CONTENT_FIELDS = [
                "content", "text", "body", "description",
                "summary", "abstract", "message",
            ]
            EXCLUDE_FIELDS = {
                "_id", "created_at", "updated_at", "source",
                "tags", "category", "id", "uuid", "_ab_cdc_cursor",
            }

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
                    if v is not None
                    and not k.startswith("_")
                    and k.lower() not in EXCLUDE_FIELDS
                ]
            content = "\n".join(content_parts)

        if not content.strip():
            continue

        doc_metadata: dict[str, Any] = {
            "source": f"airbyte:{connector_type}",
            "stream": stream_name,
            "connector_type": connector_type,
        }
        for k, v in record.items():
            if v is not None and not k.startswith("_"):
                doc_metadata[k] = _sanitize_metadata_value(v)

        documents.append(Document(page_content=content, metadata=doc_metadata))

    return documents


# ============================================================================
# Chunk statistics helpers
# ============================================================================

def _estimate_token_count(text: str) -> int:
    """Estimate token count (~1 token per 4 characters)."""
    words = len(text.split())
    return max(words, int(len(text) / 4))


# ============================================================================
# Shared text splitter (created once, reused)
# ============================================================================

_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


# ============================================================================
# Batch Endpoint
# ============================================================================

@router.post("/batch", response_model=BatchResponse)
async def ingest_batch(req: BatchRequest):
    """Receive a batch of records from destination-embedding, embed immediately.

    Called by the custom Airbyte destination connector during sync.
    Each call processes one batch:
      records → Documents → chunks → embed → PGVector

    On ``batch_index == 0`` (first batch), existing embeddings are cleared
    so the full-refresh semantic is preserved.

    On ``is_last_batch == True``, sync status is marked completed and
    optional Graph RAG rebuild is triggered.
    """
    ds_repo = DatasourceRepository()

    datasource_id = req.datasource_id

    # ------------------------------------------------------------------
    # 1. Fetch collection config
    # ------------------------------------------------------------------
    row = await ds_repo.get_collection(datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Datasource {datasource_id} not found")

    collection_name = row["name"]
    config = row.get("cmetadata", {})

    connector_type = config.get("connector_type", "unknown")
    content_fields = config.get("content_fields")

    # ------------------------------------------------------------------
    # 2. First batch → clear old embeddings + set status
    # ------------------------------------------------------------------
    if req.batch_index == 0:
        await ds_repo.delete_embeddings(datasource_id)
        logger.info("Batch 0: cleared existing embeddings for %s", datasource_id)
        await _update_progress(datasource_id, "syncing", 10)

    # ------------------------------------------------------------------
    # 3. Convert records → Documents → chunks
    # ------------------------------------------------------------------
    chunks_indexed = 0

    if req.records:
        docs = _records_to_documents(req.records, connector_type, content_fields)
        splits = _text_splitter.split_documents(docs)

        # Enrich metadata with chunk statistics
        for doc in splits:
            doc.metadata["datasource"] = datasource_id
            doc.metadata["connector_type"] = connector_type
            text = doc.page_content or ""
            doc.metadata["char_count"] = len(text)
            doc.metadata["word_count"] = len(text.split())
            doc.metadata["token_count"] = _estimate_token_count(text)

        if splits:
            # 4. Embed + write to PGVector (in thread to avoid blocking)
            vector_store = load_vector_store(collection_name)
            await asyncio.to_thread(vector_store.add_documents, splits)
            chunks_indexed = len(splits)

        logger.info(
            "Batch %d: %d records → %d docs → %d chunks for %s",
            req.batch_index, len(req.records), len(docs), chunks_indexed, datasource_id,
        )

    # ------------------------------------------------------------------
    # 5. Update progress
    # ------------------------------------------------------------------
    progress = min(90, 10 + req.batch_index * 5)
    await _update_progress(datasource_id, "syncing", progress)

    # ------------------------------------------------------------------
    # 6. Last batch → mark completed, trigger Graph RAG if enabled
    # ------------------------------------------------------------------
    if req.is_last_batch:
        await _finalize_sync(datasource_id)

    return BatchResponse(
        status="ok",
        batch_index=req.batch_index,
        records_received=len(req.records),
        chunks_indexed=chunks_indexed,
        is_last_batch=req.is_last_batch,
    )


# ============================================================================
# Source Preview Endpoint (live query from original source)
# ============================================================================


@router.post("/source-preview")
async def source_preview(req: SourcePreviewRequest):
    """Fetch sample records from the original Airbyte source.

    Used by the frontend documents tab to show raw source data
    without storing it locally.  Queries via Airbyte read API.
    """
    ds_repo = DatasourceRepository()
    mapping_repo = AirbyteMappingRepository()

    # Fetch datasource config
    row = await ds_repo.get_collection(req.datasource_id)
    if not row:
        raise HTTPException(status_code=404, detail="Datasource not found")
    config = row.get("cmetadata", {})

    # Get the Airbyte source_id from the mapping
    try:
        mapping = await mapping_repo.get(req.datasource_id)
        if not mapping:
            raise HTTPException(status_code=404, detail="No Airbyte mapping found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Use Airbyte API to discover schema and get sample records
    from service.airbyte_api_client import get_airbyte_client
    client = get_airbyte_client()

    try:
        source_data = await client.get_source(mapping["airbyte_source_id"])
        schema = await client.discover_source_schema(mapping["airbyte_source_id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach Airbyte source: {e}")

    catalog = schema.get("catalog", {})
    streams = catalog.get("streams", [])

    stream_info = []
    for s in streams:
        stream_def = s.get("stream", {})
        stream_name = stream_def.get("name", "")
        json_schema = stream_def.get("jsonSchema", {})
        properties = json_schema.get("properties", {})
        columns = list(properties.keys())
        stream_info.append({
            "name": stream_name,
            "columns": columns,
            "schema": json_schema,
        })

    return {
        "datasource_id": req.datasource_id,
        "source_name": source_data.get("name", ""),
        "connector_type": config.get("connector_type", "unknown"),
        "streams": stream_info,
        "note": "This is live schema from the source. Actual data is only stored as embeddings.",
    }


# ============================================================================
# Internal helpers
# ============================================================================

async def _update_progress(datasource_id: str, stage: str, progress: int) -> None:
    """Update sync progress in cmetadata."""
    ds_repo = DatasourceRepository()
    row = await ds_repo.get_collection(datasource_id)
    if not row:
        return
    meta = row.get("cmetadata", {})
    meta["sync_status"] = stage
    meta["sync_progress"] = progress
    await ds_repo.update_collection_metadata(datasource_id, meta)


async def _finalize_sync(datasource_id: str) -> None:
    """Mark sync as completed, store chunk stats, optionally trigger Graph RAG."""
    from service.ingestion import _trigger_graph_rag_rebuild, update_sync_status

    ds_repo = DatasourceRepository()
    mapping_repo = AirbyteMappingRepository()

    # Compute aggregate chunk stats and store in collection cmetadata
    try:
        stats = await ds_repo.get_embedding_stats(datasource_id)
        chunk_count = stats["chunk_count"]
        avg_chars = stats["avg_chunk_chars"]
        avg_tokens = stats["avg_chunk_tokens"]

        row = await ds_repo.get_collection(datasource_id)
        if row:
            meta = row.get("cmetadata", {})
            meta["chunk_stats"] = {
                "chunk_count": chunk_count,
                "avg_chunk_chars": avg_chars,
                "avg_chunk_tokens": avg_tokens,
            }
            await ds_repo.update_collection_metadata(datasource_id, meta)

        logger.info("Stored chunk stats for datasource %s: %d chunks, avg %d chars, avg %d tokens",
                    datasource_id, chunk_count, avg_chars, avg_tokens)
    except Exception:
        logger.exception("Failed to compute chunk stats for %s", datasource_id)

    await update_sync_status(datasource_id, "completed", None)
    logger.info("Sync completed for datasource %s", datasource_id)

    # Check if Graph RAG rebuild is requested
    try:
        mapping = await mapping_repo.get(datasource_id)
        if mapping and mapping.get("update_graph_rag"):
            await _trigger_graph_rag_rebuild(datasource_id)
    except Exception:
        logger.exception("Failed to trigger Graph RAG rebuild for %s", datasource_id)
