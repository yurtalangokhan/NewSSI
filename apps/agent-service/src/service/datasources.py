"""
Data Sources API Routes.

REST API endpoints for managing data sources using Airbyte OSS connectors.
All connector management is delegated to the Airbyte platform via REST API.
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
from service.sync_queue import SyncJob, get_sync_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["datasources"])


# ============================================================================
# Pydantic Models
# ============================================================================

class AirbyteConnectorConfig(BaseModel):
    """Configuration for an Airbyte-based data source."""
    connector_type: str = Field(..., description="Airbyte connector name, e.g., 'source-postgres'")
    connector_config: Dict[str, Any] = Field(..., description="Connector-specific configuration (native nested JSON)")
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
    schedule_summary: Optional[Dict[str, Any]] = None


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
    schedule: Optional[Dict[str, Any]] = None
    graph_rag_available: bool = False


class ConnectorInfoResponse(BaseModel):
    """Information about an available connector."""
    name: str
    display_name: str
    source_definition_id: str
    category: Optional[str] = None


class ConnectorSpecResponse(BaseModel):
    """Raw JSON Schema specification for a connector."""
    name: str
    display_name: str
    source_definition_id: str
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
    """List all available Airbyte source connectors."""
    from service.airbyte_connector import (
        get_connectors_by_category,
        search_connectors,
        get_connector_categories,
        get_category_labels,
    )

    try:
        if search:
            results = await search_connectors(search)
            return {
                "connectors": [c.model_dump() for c in results],
                "total": len(results),
            }

        by_category = await get_connectors_by_category()

        if category:
            filtered = by_category.get(category, [])
            return {
                "connectors": [c.model_dump() for c in filtered],
                "category": category,
                "total": len(filtered),
            }

        # Return all organized by category
        result = {
            "categories": await get_connector_categories(),
            "category_labels": await get_category_labels(),
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


@router.get("/connectors/{connector_name}/spec", response_model=ConnectorSpecResponse)
async def get_connector_specification(connector_name: str):
    """Get the raw JSON Schema configuration specification for a connector.

    Returns the native connectionSpecification — NO flattening.
    The frontend renders it via the recursive SchemaForm.
    """
    from service.airbyte_connector import get_connector_spec, _format_connector_name

    try:
        spec = await get_connector_spec(connector_name)
        return ConnectorSpecResponse(
            name=spec.name,
            display_name=_format_connector_name(connector_name),
            source_definition_id=spec.source_definition_id,
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
    """Validate a connector configuration by testing the connection.

    Config is the native nested JSON structure from the SchemaForm.
    """
    from service.airbyte_connector import validate_connector_config

    try:
        await validate_connector_config(connector_name, config)
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
    """Get available streams for a configured connector."""
    from service.airbyte_connector import get_available_streams

    try:
        streams = await get_available_streams(connector_name, config)
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

            # Fetch Airbyte mapping for schedule info
            mapping_map: Dict[str, Dict[str, Any]] = {}
            try:
                await cur.execute(
                    "SELECT datasource_id, airbyte_connection_id, update_graph_rag "
                    "FROM datasource_airbyte_mapping"
                )
                for mr in await cur.fetchall():
                    ds_id = str(mr["datasource_id"])
                    mapping_map[ds_id] = {
                        "connection_id": mr["airbyte_connection_id"],
                        "update_graph_rag": mr["update_graph_rag"],
                    }
            except Exception:
                pass  # Table may not exist yet

            results = []
            for row in rows:
                cmetadata_text = row.get("cmetadata_text", "{}")
                try:
                    meta = json.loads(cmetadata_text) if isinstance(cmetadata_text, str) else cmetadata_text or {}
                except json.JSONDecodeError:
                    meta = {}
                connector_type = meta.get("connector_type", "unknown")
                ds_id = str(row["uuid"])

                # Build schedule summary from Airbyte connection if mapped
                schedule_summary = None
                mapping = mapping_map.get(ds_id)
                if mapping:
                    try:
                        from service.airbyte_api_client import get_airbyte_client
                        client = get_airbyte_client()
                        conn_data = await client.get_connection(mapping["connection_id"])
                        sched = conn_data.get("scheduleData", {})
                        cron_data = sched.get("cron", {})
                        schedule_type = conn_data.get("scheduleType", "manual")
                        if schedule_type == "cron" and cron_data:
                            cron_expr = cron_data.get("cronExpression", "")
                            tz = cron_data.get("cronTimeZone", "UTC")
                            next_run = None
                            if cron_expr:
                                try:
                                    from service.schedule_routes import _compute_next_run
                                    next_run = _compute_next_run(cron_expr, tz)
                                except Exception:
                                    pass
                            schedule_summary = {
                                "cron_expression": cron_expr,
                                "preset": "custom",
                                "enabled": True,
                                "update_graph_rag": mapping.get("update_graph_rag", False),
                                "next_run_at": next_run,
                            }
                    except Exception:
                        pass

                results.append(DataSourceResponse(
                    id=ds_id,
                    name=row["name"],
                    connector_type=connector_type,
                    connector_display_name=_format_connector_name(connector_type),
                    streams=meta.get("streams"),
                    sync_status=meta.get("sync_status"),
                    sync_progress=meta.get("sync_progress"),
                    document_count=row.get("doc_count", 0),
                    created_at=meta.get("created_at"),
                    last_synced_at=meta.get("last_synced_at"),
                    schedule_summary=schedule_summary,
                ))

            return results


@router.post("", response_model=DataSourceResponse)
async def create_datasource(input: DataSourceInput):
    """Create a new data source.

    1. Create Airbyte source + connection + destination
    2. Store config in PG collection
    3. Store Airbyte IDs in mapping table
    """
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")

    from service.airbyte_connector import find_connector_by_name
    from service.airbyte_api_client import get_airbyte_client

    connector = await find_connector_by_name(input.config.connector_type)
    if not connector:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown connector: {input.config.connector_type}",
        )

    client = get_airbyte_client()

    # Create Airbyte source
    try:
        source = await client.create_source(
            name=input.name,
            source_definition_id=connector.source_definition_id,
            config=input.config.connector_config,
        )
        source_id = source["sourceId"]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create Airbyte source: {e}")

    # Get or create default destination
    try:
        dest_id = await client.get_or_create_default_destination()
    except Exception as e:
        # Cleanup source on failure
        try:
            await client.delete_source(source_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to setup destination: {e}")

    # Discover schema and create connection
    try:
        schema = await client.discover_source_schema(source_id)
        catalog = schema.get("catalog", {})
        catalog_streams = catalog.get("streams", [])

        if input.config.streams:
            catalog_streams = [
                s for s in catalog_streams
                if s.get("stream", {}).get("name") in input.config.streams
            ]

        for cs in catalog_streams:
            cs["config"] = {
                "syncMode": "full_refresh",
                "destinationSyncMode": "overwrite",
                "selected": True,
            }

        conn = await client.create_connection(
            source_id=source_id,
            destination_id=dest_id,
            streams=catalog_streams,
        )
        connection_id = conn["connectionId"]
    except Exception as e:
        try:
            await client.delete_source(source_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {e}")

    # Store in PG
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

    async with store.pool.connection() as conn_db:
        async with conn_db.cursor(row_factory=dict_row) as cur:
            await cur.execute("""
                INSERT INTO langchain_pg_collection (uuid, name, cmetadata)
                VALUES (%s, %s, %s)
                RETURNING *
            """, (collection_uuid, input.name, json.dumps(meta)))

            row = await cur.fetchone()

    # Store Airbyte mapping
    from service.airbyte_mapping_db import AirbyteMappingDB
    await AirbyteMappingDB.create(
        datasource_id=str(collection_uuid),
        airbyte_source_id=source_id,
        airbyte_connection_id=connection_id,
        airbyte_destination_id=dest_id,
    )

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

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
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

            # Fetch schedule from Airbyte connection
            schedule_data = None
            try:
                from service.airbyte_mapping_db import AirbyteMappingDB
                mapping = await AirbyteMappingDB.get(id)
                if mapping:
                    from service.airbyte_api_client import get_airbyte_client
                    client = get_airbyte_client()
                    conn_data = await client.get_connection(mapping["airbyte_connection_id"])
                    sched = conn_data.get("scheduleData", {})
                    cron_data = sched.get("cron", {})
                    schedule_type = conn_data.get("scheduleType", "manual")
                    cron_expr = cron_data.get("cronExpression", "")
                    tz = cron_data.get("cronTimeZone", "UTC")
                    is_enabled = schedule_type == "cron"

                    # Compute next_run_at
                    next_run = None
                    if cron_expr and is_enabled:
                        try:
                            from service.schedule_routes import _compute_next_run
                            next_run = _compute_next_run(cron_expr, tz)
                        except Exception:
                            pass

                    if schedule_type == "cron":
                        now_str = datetime.now(timezone.utc).isoformat()
                        schedule_data = {
                            "id": id,
                            "datasource_id": id,
                            "cron_expression": cron_expr,
                            "preset": "custom",
                            "enabled": is_enabled,
                            "update_graph_rag": mapping.get("update_graph_rag", False),
                            "timezone": tz,
                            "next_run_at": next_run,
                            "last_run_at": None,
                            "last_run_status": None,
                            "created_at": mapping.get("created_at", now_str),
                            "updated_at": mapping.get("updated_at", now_str),
                        }
            except Exception:
                schedule_data = None

    # Check Graph RAG service availability
    from service.ingestion import is_graph_rag_available
    graph_available = await is_graph_rag_available()

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
        schedule=schedule_data,
        graph_rag_available=graph_available,
    )


@router.post("/{id}/sync")
async def sync_datasource(id: str, background_tasks: BackgroundTasks):
    """Trigger synchronization for a data source.

    If the datasource has an Airbyte connection, triggers via Airbyte API.
    Falls back to sync queue for manual extraction.
    """
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

    # Check if there's an Airbyte mapping with graph_rag setting
    update_graph = False
    try:
        from service.airbyte_mapping_db import AirbyteMappingDB
        mapping = await AirbyteMappingDB.get(id)
        if mapping and mapping.get("update_graph_rag"):
            update_graph = True
    except Exception:
        pass

    # Enqueue through the sync queue for sequential execution
    queue = get_sync_queue()
    job = SyncJob(
        datasource_id=id,
        triggered_by="manual",
        update_graph_rag=update_graph,
    )
    enqueued = await queue.enqueue(job)
    if not enqueued:
        return {"status": "Already syncing or queued", "id": id}

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

    # Queue info
    queue = get_sync_queue()
    queue_position = queue.get_queue_position(id)
    is_active = queue.is_active(id)

    # Schedule info from Airbyte
    schedule_info = None
    try:
        from service.airbyte_mapping_db import AirbyteMappingDB
        mapping = await AirbyteMappingDB.get(id)
        if mapping:
            from service.airbyte_api_client import get_airbyte_client
            client = get_airbyte_client()
            conn_data = await client.get_connection(mapping["airbyte_connection_id"])
            sched = conn_data.get("scheduleData", {})
            cron_data = sched.get("cron", {})
            schedule_type = conn_data.get("scheduleType", "manual")
            if schedule_type == "cron" and cron_data:
                # Compute next_run_at from cron
                next_run = None
                try:
                    from service.schedule_routes import _compute_next_run
                    tz_name = cron_data.get("cronTimeZone", "UTC")
                    next_run = _compute_next_run(cron_data["cronExpression"], tz_name)
                except Exception:
                    pass

                schedule_info = {
                    "enabled": True,
                    "cron_expression": cron_data.get("cronExpression"),
                    "next_run_at": next_run,
                    "update_graph_rag": mapping.get("update_graph_rag", False),
                }
    except Exception:
        pass

    return {
        "id": id,
        "sync_status": meta.get("sync_status", "idle"),
        "sync_progress": meta.get("sync_progress", 0),
        "last_synced_at": meta.get("last_synced_at"),
        "last_error": meta.get("last_error"),
        "graph_update_status": meta.get("graph_update_status"),
        "queue_position": queue_position,
        "is_active": is_active,
        "schedule": schedule_info,
    }


@router.delete("/{id}")
async def delete_datasource(id: str):
    """Delete a data source, its embeddings, and Airbyte objects."""
    store = get_store()
    if not store or not store.pool:
        raise HTTPException(status_code=503, detail="Database not initialized")

    # Clean up Airbyte objects
    try:
        from service.airbyte_mapping_db import AirbyteMappingDB
        from service.airbyte_api_client import get_airbyte_client

        mapping = await AirbyteMappingDB.get(id)
        if mapping:
            client = get_airbyte_client()
            try:
                await client.delete_connection(mapping["airbyte_connection_id"])
            except Exception:
                logger.warning("Could not delete Airbyte connection %s", mapping["airbyte_connection_id"])
            try:
                await client.delete_source(mapping["airbyte_source_id"])
            except Exception:
                logger.warning("Could not delete Airbyte source %s", mapping["airbyte_source_id"])
            await AirbyteMappingDB.delete(id)
    except Exception as e:
        logger.error(f"Error cleaning up Airbyte objects: {e}")

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
