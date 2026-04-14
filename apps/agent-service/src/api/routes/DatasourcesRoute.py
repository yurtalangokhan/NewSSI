"""
Data Sources API Routes.

REST API endpoints for managing data sources using Airbyte OSS connectors.
All connector management is delegated to the Airbyte platform via REST API.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from controller import DataController, get_data_controller
from core.db import AirbyteMappingRepository, DatasourceRepository
from service.Schemas import (
    ChunkInfo,
    ConnectorSpecResponse,
    DataSourceDetails,
    DataSourceInput,
    DataSourceResponse,
    DataSourceUpdateInput,
    StreamInfo,
)
from service.SyncQueueService import SyncJob, get_sync_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasources", tags=["datasources"])


def _get_controller() -> DataController:
    return get_data_controller()


# Valid sync mode combinations (must match Airbyte webapp + destination spec)
_VALID_SYNC_COMBOS = {
    ("full_refresh", "overwrite"),
    ("full_refresh", "append"),
    ("incremental", "append"),
}


# ============================================================================
# Connector Discovery Endpoints
# ============================================================================


@router.get("/connectors", response_model=dict[str, Any])
async def list_connectors(
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search by name"),
):
    """List all available Airbyte source connectors."""
    from service.AirbyteConnectorService import (
        get_category_labels,
        get_connector_categories,
        get_connectors_by_category,
        search_connectors,
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
                cat: [c.model_dump() for c in connectors] for cat, connectors in by_category.items()
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
    from service.AirbyteConnectorService import _format_connector_name, get_connector_spec

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
    config: dict[str, Any],
):
    """Validate a connector configuration by testing the connection.

    Config is the native nested JSON structure from the SchemaForm.
    """
    from service.AirbyteConnectorService import validate_connector_config

    try:
        await validate_connector_config(connector_name, config)
        return {"valid": True, "message": "Connection successful"}
    except ValueError as e:
        return {"valid": False, "message": str(e)}
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return {"valid": False, "message": str(e)}


@router.post("/connectors/{connector_name}/streams", response_model=list[StreamInfo])
async def get_connector_streams(
    connector_name: str,
    config: dict[str, Any],
):
    """Get available streams for a configured connector."""
    from service.AirbyteConnectorService import get_available_streams

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


@router.get("", response_model=list[DataSourceResponse])
async def list_datasources():
    """List all configured data sources."""
    rows = await _get_controller().list_datasources()

    return [DataSourceResponse(**ds) for ds in rows]


@router.post("", response_model=DataSourceResponse)
async def create_datasource(input: DataSourceInput):
    """Create a new data source.

    1. Create Airbyte source + connection + destination
    2. Store config in PG collection
    3. Store Airbyte IDs in mapping table
    """
    ds_repo = DatasourceRepository()

    from service.AirbyteApiClientService import get_airbyte_client
    from service.AirbyteConnectorService import _format_connector_name, find_connector_by_name

    # Check for duplicate name before creating any Airbyte resources
    existing = await ds_repo.get_collection_by_name(input.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A data source named '{input.name}' already exists. Please choose a different name.",
        )

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

    # Get or create custom embedding destination
    collection_uuid = uuid4()
    try:
        dest_id = await client.get_or_create_default_destination(
            datasource_id=str(collection_uuid),
        )
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
                s
                for s in catalog_streams
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
    now = datetime.now(UTC).isoformat()

    meta = {
        "connector_type": input.config.connector_type,
        "streams": input.config.streams,
        "content_fields": input.config.content_fields,
        "created_at": now,
        "friendly_name": input.name,
    }

    try:
        row = await ds_repo.create_collection(
            collection_uuid=str(collection_uuid),
            name=input.name,
            cmetadata=meta,
        )
    except Exception as db_err:
        # Clean up Airbyte resources since PG insert failed
        try:
            await client.delete_source(source_id)
        except Exception:
            pass
        err_msg = str(db_err)
        if "UniqueViolation" in err_msg or "duplicate key" in err_msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"A data source named '{input.name}' already exists. Please choose a different name.",
            )
        raise HTTPException(status_code=500, detail="Failed to create collection")
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create collection")

    # Store Airbyte mapping
    from service.AirbyteMappingRepository import AirbyteMappingDB

    await AirbyteMappingDB.create(
        datasource_id=str(collection_uuid),
        airbyte_source_id=source_id,
        airbyte_connection_id=connection_id,
        airbyte_destination_id=dest_id,
    )

    # Auto-attach to rag-assistant
    try:
        from service.StoreService import get_assistant_from_store, update_assistant_in_store

        assistant = await get_assistant_from_store("rag-assistant")
        if assistant:
            config = assistant.get("config", {})
            if "rag_config" not in config:
                config["rag_config"] = {}
            if "collections" not in config["rag_config"]:
                config["rag_config"]["collections"] = []

            ds_id = row["uuid"]
            if ds_id not in config["rag_config"]["collections"]:
                config["rag_config"]["collections"].append(ds_id)
                await update_assistant_in_store("rag-assistant", {"config": config})
                logger.info(f"Attached datasource {ds_id} to rag-assistant")
    except Exception as e:
        logger.error(f"Failed to auto-attach datasource: {e}")

    return DataSourceResponse(
        id=row["uuid"],
        name=row["name"],
        connector_type=input.config.connector_type,
        connector_display_name=_format_connector_name(input.config.connector_type),
        streams=input.config.streams,
        created_at=now,
    )


@router.get("/{id}/details", response_model=DataSourceDetails)
async def get_datasource_details(id: str, page: int = 1, page_size: int = 10):
    """Get detailed information about a data source with paginated documents."""
    ds_repo = DatasourceRepository()

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    row = await ds_repo.get_collection(id)
    if not row:
        raise HTTPException(status_code=404, detail="DataSource not found")

    col_meta = row.get("cmetadata", {})
    connector_type = col_meta.get("connector_type", "unknown")

    # Read pre-computed chunk stats from cmetadata (written at sync finalize)
    chunk_stats = col_meta.get("chunk_stats", {})
    chunk_count = chunk_stats.get("chunk_count", 0)
    avg_chars = chunk_stats.get("avg_chunk_chars", 0)
    avg_tokens = chunk_stats.get("avg_chunk_tokens", 0)

    # If no pre-computed stats, fall back to a simple COUNT (lightweight)
    if not chunk_count:
        chunk_count = await ds_repo.count_embeddings(id)

    # Get paginated chunks
    emb_rows = await ds_repo.get_paginated_embeddings(id, limit=page_size, offset=offset)
    chunks = []
    samples = []  # backward compat
    for sr in emb_rows:
        doc_text = sr["document"] or ""
        emb_meta = sr.get("cmetadata", {}) or {}

        chunks.append(
            ChunkInfo(
                content=doc_text[:500] + "..." if len(doc_text) > 500 else doc_text,
                char_count=emb_meta.get("char_count", len(doc_text)),
                token_count=emb_meta.get(
                    "token_count", max(len(doc_text.split()), int(len(doc_text) / 4))
                ),
                word_count=emb_meta.get("word_count", len(doc_text.split())),
                source=emb_meta.get("source"),
                stream=emb_meta.get("stream"),
                connector_type=emb_meta.get("connector_type"),
                metadata=emb_meta,
            )
        )
        # backward compat
        samples.append(
            {
                "content": doc_text[:500] + "..." if len(doc_text) > 500 else doc_text,
                "metadata": emb_meta,
            }
        )

    # Fetch config from Airbyte API (no longer stored locally)
    masked_config: dict[str, Any] = {}
    airbyte_source_id: str | None = None
    try:
        from service.AirbyteMappingRepository import AirbyteMappingDB as _MappingDB

        _mapping = await _MappingDB.get(id)
        if _mapping:
            airbyte_source_id = _mapping.get("airbyte_source_id")
            from service.AirbyteApiClientService import get_airbyte_client as _get_client

            _client = _get_client()
            source_data = await _client.get_source(airbyte_source_id)
            raw_config = source_data.get("connectionConfiguration", {})
            masked_config = _mask_sensitive_config(raw_config)
    except Exception as e:
        logger.warning(f"Could not fetch config from Airbyte for {id}: {e}")
        # Fallback: try legacy cmetadata (for old datasources not yet migrated)
        legacy_config = col_meta.get("connector_config", {})
        if legacy_config:
            masked_config = _mask_sensitive_config(legacy_config)

    # Fetch schedule from Airbyte connection
    schedule_data = None
    sync_mode_val = None
    dest_sync_mode_val = None
    try:
        from service.AirbyteMappingRepository import AirbyteMappingDB

        mapping = await AirbyteMappingDB.get(id)
        if mapping:
            from service.AirbyteApiClientService import get_airbyte_client

            client = get_airbyte_client()
            conn_data = await client.get_connection(mapping["airbyte_connection_id"])

            # Extract sync mode from first stream config
            sync_catalog = conn_data.get("syncCatalog", {})
            catalog_streams = sync_catalog.get("streams", [])
            if catalog_streams:
                first_config = catalog_streams[0].get("config", {})
                sync_mode_val = first_config.get("syncMode", "full_refresh")
                dest_sync_mode_val = first_config.get("destinationSyncMode", "overwrite")

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
                    from routes.ScheduleRoute import _compute_next_run

                    next_run = _compute_next_run(cron_expr, tz)
                except Exception:
                    pass

            # Fetch last job info from Airbyte
            last_run_at_val = None
            last_run_status_val = None
            try:
                from routes.ScheduleRoute import _get_last_job_info

                last_run_at_val, last_run_status_val = await _get_last_job_info(
                    mapping["airbyte_connection_id"]
                )
            except Exception:
                pass

            if schedule_type == "cron":
                now_str = datetime.now(UTC).isoformat()
                schedule_data = {
                    "id": id,
                    "datasource_id": id,
                    "cron_expression": cron_expr,
                    "preset": "custom",
                    "enabled": is_enabled,
                    "update_graph_rag": mapping.get("update_graph_rag", False),
                    "timezone": tz,
                    "next_run_at": next_run,
                    "last_run_at": last_run_at_val,
                    "last_run_status": last_run_status_val,
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
        streams=col_meta.get("streams"),
        sync_status=col_meta.get("sync_status"),
        sync_progress=col_meta.get("sync_progress"),
        document_count=chunk_count,
        chunk_count=chunk_count,
        chunks=chunks,
        avg_chunk_tokens=avg_tokens if avg_tokens else None,
        avg_chunk_chars=avg_chars if avg_chars else None,
        sample_documents=samples,
        created_at=col_meta.get("created_at"),
        last_synced_at=col_meta.get("last_synced_at"),
        last_error=col_meta.get("last_error"),
        sync_mode=sync_mode_val,
        destination_sync_mode=dest_sync_mode_val,
        schedule=schedule_data,
        graph_rag_available=graph_available,
    )


@router.put("/{id}", response_model=DataSourceDetails)
async def update_datasource(id: str, input: DataSourceUpdateInput):
    """Update a data source's name, configuration, streams, and/or sync mode.

    Updates the Airbyte source config, connection streams/sync mode, and local metadata.
    """
    ds_repo = DatasourceRepository()

    # 1. Verify datasource exists
    row = await ds_repo.get_collection(id)
    if not row:
        raise HTTPException(status_code=404, detail="DataSource not found")

    meta = row.get("cmetadata", {})

    # 2. Get Airbyte mapping
    from service.AirbyteApiClientService import get_airbyte_client
    from service.AirbyteMappingRepository import AirbyteMappingDB

    mapping = await AirbyteMappingDB.get(id)
    if not mapping:
        raise HTTPException(status_code=400, detail="No Airbyte mapping found for this datasource")

    client = get_airbyte_client()

    # 3. Validate sync mode combination if provided
    if input.sync_mode is not None or input.destination_sync_mode is not None:
        sm = input.sync_mode or "full_refresh"
        dm = input.destination_sync_mode or "overwrite"
        if (sm, dm) not in _VALID_SYNC_COMBOS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sync mode combination: {sm} | {dm}. "
                f"Valid combos: full_refresh|overwrite, full_refresh|append, incremental|append",
            )

    # 4. Update Airbyte source config if provided
    if input.connector_config is not None:
        try:
            await client.update_source(
                source_id=mapping["airbyte_source_id"],
                config=input.connector_config,
                name=input.name,
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update Airbyte source: {e}",
            )
    elif input.name is not None:
        # Update name only
        try:
            source_data = await client.get_source(mapping["airbyte_source_id"])
            await client.update_source(
                source_id=mapping["airbyte_source_id"],
                config=source_data.get("connectionConfiguration", {}),
                name=input.name,
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update Airbyte source name: {e}",
            )

    # 5. Update connection streams and/or sync mode
    conn_update_fields: dict[str, Any] = {}

    if (
        input.streams is not None
        or input.sync_mode is not None
        or input.destination_sync_mode is not None
    ):
        try:
            conn_data = await client.get_connection(mapping["airbyte_connection_id"])
            sync_catalog = conn_data.get("syncCatalog", {})
            catalog_streams = sync_catalog.get("streams", [])

            # Filter streams if new list provided
            if input.streams is not None:
                # Re-discover to get fresh stream configs
                schema = await client.discover_source_schema(mapping["airbyte_source_id"])
                discovered_catalog = schema.get("catalog", {})
                discovered_streams = discovered_catalog.get("streams", [])

                catalog_streams = [
                    s
                    for s in discovered_streams
                    if s.get("stream", {}).get("name") in input.streams
                ]

            # Update sync mode on all streams
            effective_sync_mode = input.sync_mode or "full_refresh"
            effective_dest_mode = input.destination_sync_mode or "overwrite"
            for cs in catalog_streams:
                if "config" not in cs:
                    cs["config"] = {}
                cs["config"]["syncMode"] = effective_sync_mode
                cs["config"]["destinationSyncMode"] = effective_dest_mode
                cs["config"]["selected"] = True

            conn_update_fields["syncCatalog"] = {"streams": catalog_streams}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update connection streams: {e}",
            )

    if conn_update_fields:
        try:
            await client.update_connection(
                connection_id=mapping["airbyte_connection_id"],
                **conn_update_fields,
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to update Airbyte connection: {e}",
            )

    # 5. Update local PG metadata
    updated = False
    if input.name is not None:
        meta["friendly_name"] = input.name
        updated = True
    # connector_config is NOT stored locally anymore — Airbyte is the single source of truth
    if "connector_config" in meta:
        del meta["connector_config"]  # Clean up legacy data
        updated = True
    if input.streams is not None:
        meta["streams"] = input.streams
        updated = True

    await ds_repo.update_collection(
        id,
        name=input.name if input.name is not None else None,
        cmetadata=meta if updated else None,
    )

    # 6. Return updated details
    return await get_datasource_details(id)


@router.post("/{id}/sync")
async def sync_datasource(id: str, background_tasks: BackgroundTasks):
    """Trigger synchronization for a data source.

    If the datasource has an Airbyte connection, triggers via Airbyte API.
    Falls back to sync queue for manual extraction.
    """
    ds_repo = DatasourceRepository()

    row = await ds_repo.get_collection(id)
    if not row:
        raise HTTPException(status_code=404, detail="DataSource not found")

    # Update sync status
    meta = row.get("cmetadata", {})
    meta["sync_status"] = "starting"
    meta["sync_progress"] = 0
    await ds_repo.update_collection_metadata(id, meta)

    # Check if there's an Airbyte mapping with graph_rag setting
    update_graph = False
    try:
        from service.AirbyteMappingRepository import AirbyteMappingDB

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
    ds_repo = DatasourceRepository()

    row = await ds_repo.get_collection(id)
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
        from service.AirbyteMappingRepository import AirbyteMappingDB

        mapping = await AirbyteMappingDB.get(id)
        if mapping:
            from service.AirbyteApiClientService import get_airbyte_client

            client = get_airbyte_client()
            conn_data = await client.get_connection(mapping["airbyte_connection_id"])
            sched = conn_data.get("scheduleData", {})
            cron_data = sched.get("cron", {})
            schedule_type = conn_data.get("scheduleType", "manual")
            if schedule_type == "cron" and cron_data:
                # Compute next_run_at from cron
                next_run = None
                try:
                    from routes.ScheduleRoute import _compute_next_run

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
    ds_repo = DatasourceRepository()

    # Clean up Airbyte objects
    try:
        from service.AirbyteApiClientService import get_airbyte_client
        from service.AirbyteMappingRepository import AirbyteMappingDB

        mapping = await AirbyteMappingDB.get(id)
        if mapping:
            client = get_airbyte_client()
            try:
                await client.delete_connection(mapping["airbyte_connection_id"])
            except Exception:
                logger.warning(
                    "Could not delete Airbyte connection %s", mapping["airbyte_connection_id"]
                )
            try:
                await client.delete_source(mapping["airbyte_source_id"])
            except Exception:
                logger.warning("Could not delete Airbyte source %s", mapping["airbyte_source_id"])
            await AirbyteMappingDB.delete(id)
    except Exception as e:
        logger.error(f"Error cleaning up Airbyte objects: {e}")

    # Verify exists
    row = await ds_repo.get_collection(id)
    if not row:
        raise HTTPException(status_code=404, detail="DataSource not found")

    # Delete collection (cascade will remove embeddings via FK)
    await ds_repo.delete_collection(id)

    logger.info(f"Deleted datasource {id}")
    return {"status": "deleted", "id": id}
