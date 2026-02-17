"""
Data Sources API Routes.

This module provides REST API endpoints for managing data sources using
Airbyte connectors. Supports 600+ source connectors for databases, SaaS apps,
files, and more.
"""
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from service.store import get_store
from service.ingestion import run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["datasources"])


# ============================================================================
# Pydantic Models
# ============================================================================

class AirbyteConnectorConfig(BaseModel):
    """Configuration for an Airbyte-based data source."""
    connector_type: str = Field(..., description="Airbyte connector name, e.g., 'source-postgres'")
    connector_config: Dict[str, Any] = Field(..., description="Connector-specific configuration")
    streams: Optional[List[str]] = Field(None, description="Specific streams to sync, None = all")
    content_fields: Optional[List[str]] = Field(None, description="Fields to include in document content")


class DataSourceInput(BaseModel):
    """Input for creating a new data source."""
    name: str = Field(..., description="Human-readable name for the data source")
    config: AirbyteConnectorConfig


class DataSourceResponse(BaseModel):
    """Response model for a data source."""
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    streams: Optional[List[str]] = None
    sync_status: Optional[str] = None
    sync_progress: Optional[int] = None
    document_count: int = 0
    created_at: Optional[str] = None
    last_synced_at: Optional[str] = None


class DataSourceDetails(BaseModel):
    """Detailed information about a data source."""
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    config: Dict[str, Any]  # Masked sensitive fields
    streams: Optional[List[str]] = None
    available_streams: Optional[List[str]] = None
    sync_status: Optional[str] = None
    sync_progress: Optional[int] = None
    document_count: int = 0
    sample_documents: List[Dict[str, Any]] = []
    created_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    last_error: Optional[str] = None


class ConnectorInfo(BaseModel):
    """Information about an available connector."""
    name: str
    display_name: str
    category: Optional[str] = None


class ConnectorSpec(BaseModel):
    """Configuration specification for a connector."""
    name: str
    display_name: str
    connection_specification: Dict[str, Any]
    documentation_url: Optional[str] = None


class StreamInfo(BaseModel):
    """Information about an available stream."""
    name: str


# ============================================================================
# Connector Discovery Endpoints
# ============================================================================

@router.get("/connectors", response_model=Dict[str, Any])
async def list_connectors(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by name"),
):
    """
    List all available Airbyte source connectors.
    
    Returns connectors organized by category with option to filter.
    """
    from service.airbyte_connector import (
        get_connectors_by_category,
        search_connectors,
        get_connector_categories,
        get_category_labels,
    )
    
    try:
        if search:
            results = search_connectors(search)
            return {
                "connectors": [c.model_dump() for c in results],
                "total": len(results),
            }
        
        by_category = get_connectors_by_category()
        
        if category:
            filtered = by_category.get(category, [])
            return {
                "connectors": [c.model_dump() for c in filtered],
                "category": category,
                "total": len(filtered),
            }
        
        # Return all organized by category
        result = {
            "categories": get_connector_categories(),
            "category_labels": get_category_labels(),
            "by_category": {
                cat: [c.model_dump() for c in connectors]
                for cat, connectors in by_category.items()
            },
            "total": sum(len(c) for c in by_category.values()),
        }
        return result
        
    except Exception as e:
        logger.error(f"Failed to list connectors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connectors/{connector_name}/spec", response_model=ConnectorSpec)
async def get_connector_specification(connector_name: str):
    """
    Get the configuration specification for a connector.
    
    Returns JSON Schema describing required and optional configuration fields.
    """
    from service.airbyte_connector import get_connector_spec, _format_connector_name
    
    try:
        spec = get_connector_spec(connector_name)
        return ConnectorSpec(
            name=spec.name,
            display_name=_format_connector_name(connector_name),
            connection_specification=spec.connection_specification,
            documentation_url=spec.documentation_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get connector spec: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connectors/{connector_name}/validate")
async def validate_connector_configuration(
    connector_name: str,
    config: Dict[str, Any],
):
    """
    Validate a connector configuration by testing the connection.
    """
    from service.airbyte_connector import validate_connector_config
    
    try:
        validate_connector_config(connector_name, config)
        return {"valid": True, "message": "Connection successful"}
    except ValueError as e:
        return {"valid": False, "message": str(e)}
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {"valid": False, "message": str(e)}


@router.post("/connectors/{connector_name}/streams", response_model=List[StreamInfo])
async def get_connector_streams(
    connector_name: str,
    config: Dict[str, Any],
):
    """
    Get available streams for a configured connector.
    
    Requires valid connector configuration to discover streams.
    """
    from service.airbyte_connector import get_available_streams
    
    try:
        streams = get_available_streams(connector_name, config)
        return [StreamInfo(name=s) for s in streams]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Data Source CRUD Endpoints
# ============================================================================

def _format_connector_name(name: str) -> str:
    """Convert connector name to display format."""
    from service.airbyte_connector import _format_connector_name as fmt
    return fmt(name)


def _mask_sensitive_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive fields in configuration."""
    sensitive_keys = ["password", "api_key", "secret", "token", "credentials", "private_key"]
    masked = {}
    
    for key, value in config.items():
        if any(s in key.lower() for s in sensitive_keys):
            masked[key] = "****"
        elif isinstance(value, dict):
            masked[key] = _mask_sensitive_config(value)
        else:
            masked[key] = value
    
    return masked


@router.get("", response_model=List[DataSourceResponse])
async def list_datasources():
    """List all configured data sources."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Fetch collections that are Airbyte data sources
            await cur.execute("""
                SELECT c.uuid, c.name, c.cmetadata::text as cmetadata_text,
                       COUNT(e.id) as doc_count
                FROM langchain_pg_collection c
                LEFT JOIN langchain_pg_embedding e ON e.collection_id = c.uuid
                WHERE c.cmetadata::jsonb ? 'connector_type'
                GROUP BY c.uuid, c.name, c.cmetadata::text
            """)
            rows = await cur.fetchall()
            
            results = []
            for row in rows:
                # Parse cmetadata from text string
                cmetadata_text = row.get("cmetadata_text", "{}")
                try:
                    meta = json.loads(cmetadata_text) if isinstance(cmetadata_text, str) else cmetadata_text or {}
                except json.JSONDecodeError:
                    meta = {}
                connector_type = meta.get("connector_type", "unknown")
                
                results.append(DataSourceResponse(
                    id=str(row["uuid"]),
                    name=row["name"],
                    connector_type=connector_type,
                    connector_display_name=_format_connector_name(connector_type),
                    streams=meta.get("streams"),
                    sync_status=meta.get("sync_status"),
                    sync_progress=meta.get("sync_progress"),
                    document_count=row.get("doc_count", 0),
                    created_at=meta.get("created_at"),
                    last_synced_at=meta.get("last_synced_at"),
                ))
            
            return results


@router.post("", response_model=DataSourceResponse)
async def create_datasource(input: DataSourceInput):
    """
    Create a new data source using an Airbyte connector.
    
    The data source is created but not synced. Call POST /{id}/sync to start syncing.
    """
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    # Validate connector exists
    from service.airbyte_connector import get_available_connectors
    available = get_available_connectors()
    if input.config.connector_type not in available:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown connector: {input.config.connector_type}"
        )
    
    collection_uuid = uuid4()
    now = datetime.now(timezone.utc).isoformat()
    
    meta = {
        "connector_type": input.config.connector_type,
        "connector_config": input.config.connector_config,
        "streams": input.config.streams,
        "content_fields": input.config.content_fields,
        "created_at": now,
        "friendly_name": input.name,
    }
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                INSERT INTO langchain_pg_collection (uuid, name, cmetadata)
                VALUES (%s, %s, %s)
                RETURNING *
            """, (collection_uuid, input.name, json.dumps(meta)))
            
            row = await cur.fetchone()
            
            # Auto-attach to rag-assistant
            try:
                from service.store import get_assistant_from_store, update_assistant_in_store
                assistant = await get_assistant_from_store("rag-assistant")
                if assistant:
                    config = assistant.get("config", {})
                    if "rag_config" not in config:
                        config["rag_config"] = {}
                    if "collections" not in config["rag_config"]:
                        config["rag_config"]["collections"] = []
                    
                    ds_id = str(row["uuid"])
                    if ds_id not in config["rag_config"]["collections"]:
                        config["rag_config"]["collections"].append(ds_id)
                        await update_assistant_in_store("rag-assistant", {"config": config})
                        logger.info(f"Attached datasource {ds_id} to rag-assistant")
            except Exception as e:
                logger.error(f"Failed to auto-attach datasource: {e}")
            
            return DataSourceResponse(
                id=str(row["uuid"]),
                name=row["name"],
                connector_type=input.config.connector_type,
                connector_display_name=_format_connector_name(input.config.connector_type),
                streams=input.config.streams,
                created_at=now,
            )


@router.get("/{id}/details", response_model=DataSourceDetails)
async def get_datasource_details(id: str, page: int = 1, page_size: int = 10):
    """Get detailed information about a data source with paginated documents."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    # Ensure valid pagination params
    page = max(1, page)
    page_size = min(max(1, page_size), 100)  # Max 100 per page
    offset = (page - 1) * page_size
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM langchain_pg_collection WHERE uuid = %s",
                (id,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="DataSource not found")
            
            meta = row.get("cmetadata", {})
            connector_type = meta.get("connector_type", "unknown")
            
            # Get document count
            await cur.execute(
                "SELECT COUNT(*) as count FROM langchain_pg_embedding WHERE collection_id = %s",
                (id,)
            )
            count_row = await cur.fetchone()
            doc_count = count_row["count"] if count_row else 0
            
            # Get paginated documents
            await cur.execute(
                """SELECT document, cmetadata FROM langchain_pg_embedding 
                   WHERE collection_id = %s 
                   ORDER BY id
                   LIMIT %s OFFSET %s""",
                (id, page_size, offset)
            )
            sample_rows = await cur.fetchall()
            samples = []
            for sr in sample_rows:
                doc_text = sr["document"]
                samples.append({
                    "content": doc_text[:500] + "..." if len(doc_text) > 500 else doc_text,
                    "metadata": sr.get("cmetadata", {}),
                })
            
            # Mask sensitive config
            masked_config = _mask_sensitive_config(meta.get("connector_config", {}))
            
            return DataSourceDetails(
                id=str(row["uuid"]),
                name=row["name"],
                connector_type=connector_type,
                connector_display_name=_format_connector_name(connector_type),
                config=masked_config,
                streams=meta.get("streams"),
                sync_status=meta.get("sync_status"),
                sync_progress=meta.get("sync_progress"),
                document_count=doc_count,
                sample_documents=samples,
                created_at=meta.get("created_at"),
                last_synced_at=meta.get("last_synced_at"),
                last_error=meta.get("last_error"),
            )


@router.post("/{id}/sync")
async def sync_datasource(id: str, background_tasks: BackgroundTasks):
    """Trigger synchronization for a data source."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (id,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="DataSource not found")
            
            # Update sync status
            meta = row["cmetadata"]
            meta["sync_status"] = "starting"
            meta["sync_progress"] = 0
            await cur.execute(
                "UPDATE langchain_pg_collection SET cmetadata = %s WHERE uuid = %s",
                (json.dumps(meta), id)
            )
    
    background_tasks.add_task(run_ingestion, id)
    return {"status": "Sync started", "id": id}


@router.get("/{id}/status")
async def get_sync_status(id: str):
    """Get current sync status for real-time progress tracking."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT cmetadata FROM langchain_pg_collection WHERE uuid = %s",
                (id,)
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="DataSource not found")
            
            meta = row.get("cmetadata", {})
            return {
                "id": id,
                "sync_status": meta.get("sync_status", "idle"),
                "sync_progress": meta.get("sync_progress", 0),
                "last_synced_at": meta.get("last_synced_at"),
                "last_error": meta.get("last_error"),
            }


@router.delete("/{id}")
async def delete_datasource(id: str):
    """Delete a data source and all its embeddings."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    async with store.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Verify exists
            await cur.execute(
                "SELECT uuid FROM langchain_pg_collection WHERE uuid = %s",
                (id,)
            )
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="DataSource not found")
            
            # Delete embeddings
            await cur.execute(
                "DELETE FROM langchain_pg_embedding WHERE collection_id = %s",
                (id,)
            )
            
            # Delete collection
            await cur.execute(
                "DELETE FROM langchain_pg_collection WHERE uuid = %s",
                (id,)
            )
    
    logger.info(f"Deleted datasource {id}")
    return {"status": "deleted", "id": id}
