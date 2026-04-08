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

import logging

from fastapi import APIRouter

from controller import IngestController, get_ingest_controller
from service.Schemas import BatchRequest, BatchResponse, SourcePreviewRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])


def _get_controller() -> IngestController:
    """Get the singleton IngestController instance."""
    return get_ingest_controller()


# =============================================================================
# Batch Endpoint
# =============================================================================


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
    ctrl = _get_controller()
    return await ctrl.ingest_batch(req)


# ============================================================================
# Source Preview Endpoint (live query from original source)
# ============================================================================


@router.post("/source-preview")
async def source_preview(req: SourcePreviewRequest):
    """Fetch sample records from the original Airbyte source.

    Used by the frontend documents tab to show raw source data
    without storing it locally.  Queries via Airbyte read API.
    """
    ctrl = _get_controller()
    return await ctrl.source_preview(req)

