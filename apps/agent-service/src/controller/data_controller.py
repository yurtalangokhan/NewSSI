"""Data controller - handles datasources, schedules, and ingestion domain logic."""

from typing import Any

from controller.base import BaseController
from core.db import AirbyteMappingRepository, DatasourceRepository
from service.AirbyteMappingRepository import AirbyteMappingDB
from service.SyncQueueService import SyncJob, get_sync_queue


class DataController(BaseController):
    """Controller for datasources, schedules, and ingestion domain.

    Injects:
    - DatasourceRepository: for datasource persistent storage
    - AirbyteMappingRepository: for Airbyte mapping storage
    - AirbyteMappingDB: for Airbyte mapping operations
    """

    def __init__(
        self,
        ds_repo: DatasourceRepository | None = None,
        mapping_repo: AirbyteMappingRepository | None = None,
    ):
        self._ds_repo = ds_repo or DatasourceRepository()
        self._mapping_repo = mapping_repo or AirbyteMappingRepository()

    # =========================================================================
    # DataSource CRUD
    # =========================================================================

    async def list_datasources(self) -> list[dict[str, Any]]:
        """List all configured data sources with their schedule summaries."""
        rows = await self._ds_repo.list_datasource_collections()
        if not rows:
            return []

        mapping_repo = AirbyteMappingRepository()
        mapping_map: dict[str, dict[str, Any]] = {}
        try:
            all_mappings = await mapping_repo.list_all()
            for m in all_mappings:
                mapping_map[m["datasource_id"]] = {
                    "connection_id": m["airbyte_connection_id"],
                    "update_graph_rag": m["update_graph_rag"],
                }
        except Exception:
            pass

        # Collect names that need a Milvus fallback count, then query in one connection.
        from agents.tools import _count_milvus_entities_batch

        needs_milvus = [
            row.get("name", "")
            for row in rows
            if not (row.get("cmetadata", {}) or {}).get("chunk_stats", {}).get("chunk_count")
            and not row.get("doc_count")
            and row.get("name")
        ]
        milvus_counts = _count_milvus_entities_batch(needs_milvus) if needs_milvus else {}

        results = []
        for row in rows:
            meta = row.get("cmetadata", {})
            connector_type = meta.get("connector_type", "unknown")
            ds_id = str(row["uuid"])
            chunk_stats = meta.get("chunk_stats", {}) if isinstance(meta, dict) else {}
            chunk_count = chunk_stats.get("chunk_count", 0)
            if not chunk_count:
                chunk_count = row.get("doc_count", 0)
            if not chunk_count:
                chunk_count = milvus_counts.get(row.get("name", ""), 0)

            schedule_summary = None
            mapping = mapping_map.get(ds_id)
            if mapping:
                try:
                    from service.AirbyteApiClientService import get_airbyte_client

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
                                from service.ScheduleRepository import _compute_next_run

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

            results.append(
                {
                    "id": ds_id,
                    "name": row["name"],
                    "connector_type": connector_type,
                    "connector_display_name": self._format_connector_name(connector_type),
                    "streams": meta.get("streams"),
                    "sync_status": meta.get("sync_status"),
                    "sync_progress": meta.get("sync_progress"),
                    "document_count": chunk_count,
                    "created_at": meta.get("created_at"),
                    "last_synced_at": meta.get("last_synced_at"),
                    "schedule_summary": schedule_summary,
                }
            )

        return results

    def _format_connector_name(self, name: str) -> str:
        """Convert connector name to display format."""
        from service.AirbyteConnectorService import _format_connector_name as fmt

        return fmt(name)

    def _mask_sensitive_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Mask sensitive fields in configuration."""
        sensitive_keys = ["password", "api_key", "secret", "token", "credentials", "private_key"]
        masked = {}

        for key, value in config.items():
            if any(s in key.lower() for s in sensitive_keys):
                masked[key] = "****"
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_config(value)
            else:
                masked[key] = value

        return masked

    async def get_datasource(self, datasource_id: str) -> dict[str, Any] | None:
        """Get a datasource by ID."""
        return await self._ds_repo.get_collection(datasource_id)

    async def create_datasource(
        self,
        name: str,
        connector_type: str,
        connector_config: dict[str, Any],
        streams: list[str] | None = None,
        content_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new data source."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from service.AirbyteApiClientService import get_airbyte_client
        from service.AirbyteConnectorService import find_connector_by_name

        connector = await find_connector_by_name(connector_type)
        if not connector:
            self._raise_bad_request(f"Unknown connector: {connector_type}")

        client = get_airbyte_client()

        try:
            source = await client.create_source(
                name=name,
                source_definition_id=connector.source_definition_id,
                config=connector_config,
            )
            source_id = source["sourceId"]
        except Exception as e:
            self._raise_bad_request(f"Failed to create Airbyte source: {e}")

        collection_uuid = uuid4()
        try:
            dest_id = await client.get_or_create_default_destination(
                datasource_id=str(collection_uuid),
            )
        except Exception as e:
            try:
                await client.delete_source(source_id)
            except Exception:
                pass
            self._raise_internal_error(f"Failed to setup destination: {e}")

        try:
            schema = await client.discover_source_schema(source_id)
            catalog = schema.get("catalog", {})
            catalog_streams = catalog.get("streams", [])

            if streams:
                catalog_streams = [
                    s
                    for s in catalog_streams
                    if s.get("stream", {}).get("name") in streams
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
            self._raise_internal_error(f"Failed to create connection: {e}")

        now = datetime.now(UTC).isoformat()
        meta = {
            "connector_type": connector_type,
            "streams": streams,
            "content_fields": content_fields,
            "created_at": now,
            "friendly_name": name,
        }

        row = await self._ds_repo.create_collection(
            collection_uuid=str(collection_uuid),
            name=name,
            cmetadata=meta,
        )
        if not row:
            self._raise_internal_error("Failed to create collection")

        await AirbyteMappingDB.create(
            datasource_id=str(collection_uuid),
            airbyte_source_id=source_id,
            airbyte_connection_id=connection_id,
            airbyte_destination_id=dest_id,
        )

        return {
            "id": str(row["uuid"]),
            "name": row["name"],
            "connector_type": connector_type,
            "created_at": now,
        }

    async def update_datasource(
        self,
        datasource_id: str,
        name: str | None = None,
        connector_config: dict[str, Any] | None = None,
        streams: list[str] | None = None,
        sync_mode: str | None = None,
        destination_sync_mode: str | None = None,
    ) -> dict[str, Any]:
        """Update a data source."""
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found(f"DataSource {datasource_id} not found")

        meta = row.get("cmetadata", {})

        from service.AirbyteApiClientService import get_airbyte_client
        from service.AirbyteMappingRepository import AirbyteMappingDB

        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            self._raise_bad_request("No Airbyte mapping found for this datasource")

        client = get_airbyte_client()

        valid_combos = {
            ("full_refresh", "overwrite"),
            ("full_refresh", "append"),
            ("incremental", "append"),
        }
        sm = sync_mode or "full_refresh"
        dm = destination_sync_mode or "overwrite"
        if (sm, dm) not in valid_combos:
            self._raise_bad_request(
                f"Invalid sync mode combination: {sm} | {dm}. "
                f"Valid combos: full_refresh|overwrite, full_refresh|append, incremental|append"
            )

        if connector_config is not None:
            try:
                await client.update_source(
                    source_id=mapping["airbyte_source_id"],
                    config=connector_config,
                    name=name,
                )
            except Exception as e:
                self._raise_bad_request(f"Failed to update Airbyte source: {e}")
        elif name is not None:
            source_data = await client.get_source(mapping["airbyte_source_id"])
            try:
                await client.update_source(
                    source_id=mapping["airbyte_source_id"],
                    config=source_data.get("connectionConfiguration", {}),
                    name=name,
                )
            except Exception as e:
                self._raise_bad_request(f"Failed to update Airbyte source name: {e}")

        conn_update_fields: dict[str, Any] = {}
        if (
            streams is not None
            or sync_mode is not None
            or destination_sync_mode is not None
        ):
            try:
                conn_data = await client.get_connection(mapping["airbyte_connection_id"])
                sync_catalog = conn_data.get("syncCatalog", {})
                catalog_streams = sync_catalog.get("streams", [])

                if streams is not None:
                    schema = await client.discover_source_schema(mapping["airbyte_source_id"])
                    discovered_catalog = schema.get("catalog", {})
                    discovered_streams = discovered_catalog.get("streams", [])
                    catalog_streams = [
                        s
                        for s in discovered_streams
                        if s.get("stream", {}).get("name") in streams
                    ]

                effective_sync_mode = sync_mode or "full_refresh"
                effective_dest_mode = destination_sync_mode or "overwrite"
                for cs in catalog_streams:
                    if "config" not in cs:
                        cs["config"] = {}
                    cs["config"]["syncMode"] = effective_sync_mode
                    cs["config"]["destinationSyncMode"] = effective_dest_mode
                    cs["config"]["selected"] = True

                conn_update_fields["syncCatalog"] = {"streams": catalog_streams}
            except Exception as e:
                self._raise_bad_request(f"Failed to update connection streams: {e}")

        if conn_update_fields:
            try:
                await client.update_connection(
                    connection_id=mapping["airbyte_connection_id"],
                    **conn_update_fields,
                )
            except Exception as e:
                self._raise_bad_request(f"Failed to update Airbyte connection: {e}")

        updated = False
        if name is not None:
            meta["friendly_name"] = name
            updated = True
        if "connector_config" in meta:
            del meta["connector_config"]
            updated = True
        if streams is not None:
            meta["streams"] = streams
            updated = True

        await self._ds_repo.update_collection(
            datasource_id,
            name=name if name is not None else None,
            cmetadata=meta if updated else None,
        )

        return await self.get_datasource_details(datasource_id)

    async def delete_datasource(self, datasource_id: str) -> dict[str, Any]:
        """Delete a data source."""
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found(f"DataSource {datasource_id} not found")

        from service.AirbyteApiClientService import get_airbyte_client
        from service.AirbyteMappingRepository import AirbyteMappingDB

        mapping = await AirbyteMappingDB.get(datasource_id)
        if mapping:
            client = get_airbyte_client()
            try:
                await client.delete_connection(mapping["airbyte_connection_id"])
            except Exception:
                pass
            try:
                await client.delete_source(mapping["airbyte_source_id"])
            except Exception:
                pass
            await AirbyteMappingDB.delete(datasource_id)

        await self._ds_repo.delete_collection(datasource_id)
        return {"status": "deleted", "id": datasource_id}

    async def get_datasource_details(
        self,
        datasource_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Get detailed information about a data source."""
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found(f"DataSource {datasource_id} not found")

        col_meta = row.get("cmetadata", {})
        connector_type = col_meta.get("connector_type", "unknown")

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        chunk_stats = col_meta.get("chunk_stats", {})
        chunk_count = chunk_stats.get("chunk_count", 0)
        avg_chars = chunk_stats.get("avg_chunk_chars", 0)
        avg_tokens = chunk_stats.get("avg_chunk_tokens", 0)

        if not chunk_count:
            chunk_count = await self._ds_repo.count_embeddings(datasource_id)

        emb_rows = await self._ds_repo.get_paginated_embeddings(
            datasource_id, limit=page_size, offset=offset
        )
        chunks = []
        for sr in emb_rows:
            doc_text = sr["document"] or ""
            emb_meta = sr.get("cmetadata", {}) or {}
            chunks.append(
                {
                    "content": doc_text[:500] + "..." if len(doc_text) > 500 else doc_text,
                    "char_count": emb_meta.get("char_count", len(doc_text)),
                    "token_count": emb_meta.get(
                        "token_count", max(len(doc_text.split()), int(len(doc_text) / 4))
                    ),
                    "word_count": emb_meta.get("word_count", len(doc_text.split())),
                    "source": emb_meta.get("source"),
                    "stream": emb_meta.get("stream"),
                    "connector_type": emb_meta.get("connector_type"),
                    "metadata": emb_meta,
                }
            )

        return {
            "id": str(row["uuid"]),
            "name": row["name"],
            "connector_type": connector_type,
            "streams": col_meta.get("streams"),
            "sync_status": col_meta.get("sync_status"),
            "sync_progress": col_meta.get("sync_progress"),
            "document_count": chunk_count,
            "chunks": chunks,
            "created_at": col_meta.get("created_at"),
            "last_synced_at": col_meta.get("last_synced_at"),
        }

    # =========================================================================
    # Sync operations
    # =========================================================================

    async def trigger_sync(
        self,
        datasource_id: str,
        triggered_by: str = "manual",
    ) -> dict[str, Any]:
        """Trigger synchronization for a data source."""
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found(f"DataSource {datasource_id} not found")

        meta = row.get("cmetadata", {})
        meta["sync_status"] = "starting"
        meta["sync_progress"] = 0
        await self._ds_repo.update_collection_metadata(datasource_id, meta)

        update_graph = False
        try:
            mapping = await AirbyteMappingDB.get(datasource_id)
            if mapping and mapping.get("update_graph_rag"):
                update_graph = True
        except Exception:
            pass

        queue = get_sync_queue()
        job = SyncJob(
            datasource_id=datasource_id,
            triggered_by=triggered_by,
            update_graph_rag=update_graph,
        )
        enqueued = await queue.enqueue(job)
        if not enqueued:
            return {"status": "Already syncing or queued", "id": datasource_id}

        return {"status": "Sync started", "id": datasource_id}

    async def get_sync_status(self, datasource_id: str) -> dict[str, Any]:
        """Get current sync status."""
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found(f"DataSource {datasource_id} not found")

        meta = row.get("cmetadata", {})

        queue = get_sync_queue()
        queue_position = queue.get_queue_position(datasource_id)
        is_active = queue.is_active(datasource_id)

        return {
            "id": datasource_id,
            "sync_status": meta.get("sync_status", "idle"),
            "sync_progress": meta.get("sync_progress", 0),
            "last_synced_at": meta.get("last_synced_at"),
            "last_error": meta.get("last_error"),
            "queue_position": queue_position,
            "is_active": is_active,
        }

    # =========================================================================
    # Schedule operations
    # =========================================================================

    async def list_schedules(self) -> list[dict[str, Any]]:
        """List all sync schedules."""
        mappings = await AirbyteMappingDB.list_all()
        if not mappings:
            return []

        from service.AirbyteApiClientService import get_airbyte_client

        items = []
        client = get_airbyte_client()
        for mapping in mappings:
            try:
                conn_id = mapping["airbyte_connection_id"]
                conn_data = await client.get_connection(conn_id)
                sched = conn_data.get("scheduleData", {})
                cron_data = sched.get("cron", {})
                schedule_type = conn_data.get("scheduleType", "manual")

                if schedule_type != "cron":
                    continue

                cron_expr = cron_data.get("cronExpression", "")
                tz = cron_data.get("cronTimeZone", "UTC")

                items.append({
                    "id": mapping["datasource_id"],
                    "datasource_id": mapping["datasource_id"],
                    "cron_expression": cron_expr,
                    "enabled": True,
                    "update_graph_rag": mapping.get("update_graph_rag", False),
                    "timezone": tz,
                })
            except Exception:
                continue

        return items

    async def get_schedule(self, datasource_id: str) -> dict[str, Any] | None:
        """Get schedule for a datasource."""
        mapping = await AirbyteMappingDB.get(datasource_id)
        if not mapping:
            return None

        from service.AirbyteApiClientService import get_airbyte_client

        client = get_airbyte_client()
        conn_id = mapping["airbyte_connection_id"]
        conn_data = await client.get_connection(conn_id)

        sched = conn_data.get("scheduleData", {})
        cron_data = sched.get("cron", {})
        schedule_type = conn_data.get("scheduleType", "manual")

        if schedule_type != "cron":
            return None

        return {
            "id": datasource_id,
            "datasource_id": datasource_id,
            "cron_expression": cron_data.get("cronExpression", ""),
            "enabled": True,
            "update_graph_rag": mapping.get("update_graph_rag", False),
            "timezone": cron_data.get("cronTimeZone", "UTC"),
        }


# Singleton instance
_data_controller: DataController | None = None


def get_data_controller() -> DataController:
    """Get the singleton DataController instance."""
    global _data_controller
    if _data_controller is None:
        _data_controller = DataController()
    return _data_controller