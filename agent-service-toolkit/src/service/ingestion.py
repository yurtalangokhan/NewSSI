"""
Data Ingestion Module.

This module handles the background ingestion of data from Airbyte sources
into the vector store for RAG operations.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg.rows import dict_row

from service.store import get_store
from agents.tools import load_vector_store

# LangConnect base URL for Graph RAG rebuild requests
LANGCONNECT_BASE_URL = os.environ.get("LANGCONNECT_API_URL", "http://langconnect-api:8083")
# Internal service token for authenticating with LangConnect
LANGCONNECT_SERVICE_TOKEN = os.environ.get("LANGCONNECT_SERVICE_TOKEN", "")

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Graph RAG availability check (cached)
# ------------------------------------------------------------------

_graph_rag_cache: dict = {"available": False, "checked_at": 0.0}
_GRAPH_RAG_CACHE_TTL = 300  # seconds


async def is_graph_rag_available() -> bool:
    """Check whether the LangConnect Graph RAG service is reachable.

    The result is cached for ``_GRAPH_RAG_CACHE_TTL`` seconds so that
    every details request does not incur a network round-trip.
    """
    now = time.time()
    if now - _graph_rag_cache["checked_at"] < _GRAPH_RAG_CACHE_TTL:
        return _graph_rag_cache["available"]

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            resp = await client.get(f"{LANGCONNECT_BASE_URL}/docs")
            available = resp.status_code < 500
    except Exception:
        available = False

    _graph_rag_cache["available"] = available
    _graph_rag_cache["checked_at"] = now
    return available


async def run_ingestion(datasource_id: str, update_graph_rag: bool = False):
    """
    Background task to ingest data from an Airbyte source.
    
    Workflow:
    1. Fetch config from database
    2. Extract data using PyAirbyte
    3. Split into chunks
    4. Index into vector store
    5. (Optional) Trigger Graph RAG rebuild via LangConnect
    """
    logger.info(f"Starting ingestion for datasource {datasource_id}")
    
    try:
        # 1. Fetch configuration
        store = get_store()
        if not store or not store.pool:
            logger.error("Store not initialized")
            return
        
        async with store.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT name, cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                    (datasource_id,)
                )
                row = await cur.fetchone()
                if not row:
                    logger.error(f"Datasource {datasource_id} not found")
                    return
                
                collection_name = row["name"]
                config = row["cmetadata"]
                logger.info(f"Loaded config for {datasource_id}")
        
        # 2. Update status - Fetching
        await update_sync_progress(datasource_id, "fetching", 10)
        
        # 3. Extract documents using PyAirbyte
        connector_type = config.get("connector_type")
        connector_config = config.get("connector_config", {})
        streams = config.get("streams")
        content_fields = config.get("content_fields")
        
        if not connector_type:
            logger.error(f"No connector_type in config for {datasource_id}")
            await update_sync_status(datasource_id, "error", "Missing connector_type in configuration")
            return
        
        try:
            from service.airbyte_connector import extract_documents_async
            
            logger.info(f"Extracting data from {connector_type}...")
            docs = await extract_documents_async(
                connector_type,
                connector_config,
                streams,
                content_fields,
            )
            
        except Exception as e:
            logger.error(f"Failed to extract data for {datasource_id}: {e}")
            await update_sync_status(datasource_id, "error", str(e))
            return
        
        logger.info(f"Extracted {len(docs)} documents from {connector_type}")
        await update_sync_progress(datasource_id, "fetching", 30)
        
        if not docs:
            logger.warning("No documents found to index")
            await update_sync_status(datasource_id, "completed", "No documents found")
            return
        
        # 4. Split documents
        await update_sync_progress(datasource_id, "splitting", 40)
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
        splits = text_splitter.split_documents(docs)
        
        # Enrich metadata
        for doc in splits:
            doc.metadata["datasource"] = datasource_id
            doc.metadata["connector_type"] = connector_type
        
        logger.info(f"Split into {len(splits)} chunks")
        await update_sync_progress(datasource_id, "splitting", 50)
        
        # 5. Clear existing embeddings for this datasource
        await update_sync_progress(datasource_id, "indexing", 55)
        
        async with store.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM langchain_pg_embedding WHERE collection_id = %s",
                    (datasource_id,)
                )
                logger.info(f"Cleared existing embeddings for {datasource_id}")
        
        # 6. Index into vector store
        await update_sync_progress(datasource_id, "indexing", 60)
        
        vector_store = load_vector_store(collection_name)
        
        # Run indexing in thread to avoid blocking
        await asyncio.to_thread(vector_store.add_documents, splits)
        
        logger.info(f"Indexed {len(splits)} chunks for {datasource_id}")
        await update_sync_progress(datasource_id, "indexing", 95)
        
        # 7. Mark sync completed
        await update_sync_status(datasource_id, "completed", None)
        logger.info(f"Ingestion completed for {datasource_id}")

        # 8. Optionally trigger Graph RAG rebuild
        if update_graph_rag:
            await _trigger_graph_rag_rebuild(datasource_id)
        
    except Exception as e:
        logger.exception(f"Unhandled error in ingestion for {datasource_id}")
        await update_sync_status(datasource_id, "error", str(e))


async def update_sync_status(uuid_str: str, status: str, error_msg: str | None):
    """Update final sync status with timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    
    store = get_store()
    if not store or not store.pool:
        logger.error("Store not initialized")
        return
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (uuid_str,)
            )
            row = await cur.fetchone()
            if not row:
                return
            
            meta = row["cmetadata"]
            meta["sync_status"] = status
            meta["sync_progress"] = 100 if status == "completed" else 0
            meta["last_synced_at"] = now
            
            if error_msg:
                meta["last_error"] = error_msg
            else:
                meta.pop("last_error", None)
            
            await cur.execute(
                "UPDATE langchain_pg_collection SET cmetadata = %s WHERE uuid = %s",
                (json.dumps(meta), uuid_str)
            )


async def update_sync_progress(uuid_str: str, stage: str, progress: int):
    """Update sync progress for real-time tracking."""
    store = get_store()
    if not store or not store.pool:
        return
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (uuid_str,)
            )
            row = await cur.fetchone()
            if not row:
                return
            
            meta = row["cmetadata"]
            meta["sync_status"] = stage
            meta["sync_progress"] = progress
            
            await cur.execute(
                "UPDATE langchain_pg_collection SET cmetadata = %s WHERE uuid = %s",
                (json.dumps(meta), uuid_str)
            )


# ------------------------------------------------------------------
# Graph RAG rebuild via httpx → LangConnect
# ------------------------------------------------------------------


async def _trigger_graph_rag_rebuild(datasource_id: str) -> None:
    """Call LangConnect's ``POST /api/graph/build`` to rebuild the knowledge graph.

    Uses httpx with an internal service token for authentication.
    Updates cmetadata with graph_update_status for UI feedback.
    """
    logger.info("Triggering Graph RAG rebuild for %s", datasource_id)
    await _update_graph_status(datasource_id, "graph_rebuilding")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if LANGCONNECT_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {LANGCONNECT_SERVICE_TOKEN}"
    else:
        headers["X-Internal-Service"] = "agent-service"

    payload = {"collection_id": datasource_id}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
            # 1. Trigger graph build
            resp = await client.post(
                f"{LANGCONNECT_BASE_URL}/api/graph/build",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            build_data = resp.json()
            logger.info(
                "Graph build triggered for %s: %s", datasource_id, build_data.get("status")
            )

            # 2. Poll build progress until complete
            max_polls = 600  # 10 min max (1s interval)
            for _ in range(max_polls):
                await asyncio.sleep(1.0)
                status_resp = await client.get(
                    f"{LANGCONNECT_BASE_URL}/api/graph/build/{datasource_id}/status",
                    headers=headers,
                )
                status_resp.raise_for_status()
                progress = status_resp.json()
                current_status = progress.get("status", "")

                if current_status == "completed":
                    logger.info("Graph RAG rebuild completed for %s", datasource_id)
                    await _update_graph_status(datasource_id, "graph_completed")
                    return
                elif current_status == "failed":
                    err = progress.get("error", "Unknown graph build error")
                    logger.error("Graph RAG rebuild failed for %s: %s", datasource_id, err)
                    await _update_graph_status(datasource_id, "graph_failed", err)
                    return

            # Timed out
            logger.warning("Graph RAG rebuild timed out for %s", datasource_id)
            await _update_graph_status(datasource_id, "graph_timeout")

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Graph RAG rebuild HTTP error for %s: %s %s",
            datasource_id,
            exc.response.status_code,
            exc.response.text[:200],
        )
        await _update_graph_status(datasource_id, "graph_failed", str(exc))
    except httpx.ConnectError:
        logger.warning(
            "Graph RAG service not reachable at %s for datasource %s – skipping graph rebuild",
            LANGCONNECT_BASE_URL,
            datasource_id,
        )
        await _update_graph_status(datasource_id, "graph_unavailable")
    except Exception as exc:
        logger.exception("Graph RAG rebuild error for %s", datasource_id)
        await _update_graph_status(datasource_id, "graph_failed", str(exc))


async def _update_graph_status(
    uuid_str: str, graph_status: str, error: str | None = None
) -> None:
    """Write graph_update_status into cmetadata for UI feedback."""
    store = get_store()
    if not store or not store.pool:
        return

    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (uuid_str,),
            )
            row = await cur.fetchone()
            if not row:
                return

            meta = row["cmetadata"]
            meta["graph_update_status"] = graph_status
            if error:
                meta["graph_update_error"] = error
            else:
                meta.pop("graph_update_error", None)

            await cur.execute(
                "UPDATE langchain_pg_collection SET cmetadata = %s WHERE uuid = %s",
                (json.dumps(meta), uuid_str),
            )
