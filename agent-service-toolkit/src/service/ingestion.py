"""
Data Ingestion Module.

This module handles the background ingestion of data from Airbyte sources
into the vector store for RAG operations.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg.rows import dict_row

from service.store import get_store
from agents.tools import load_vector_store

logger = logging.getLogger(__name__)


async def run_ingestion(datasource_id: str):
    """
    Background task to ingest data from an Airbyte source.
    
    Workflow:
    1. Fetch config from database
    2. Extract data using PyAirbyte
    3. Split into chunks
    4. Index into vector store
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
        
        # 7. Mark completed
        await update_sync_status(datasource_id, "completed", None)
        logger.info(f"Ingestion completed for {datasource_id}")
        
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
