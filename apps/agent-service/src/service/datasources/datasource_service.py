"""Datasource domain service.

A datasource is a RAG collection filled by a connector. This service owns its
lifecycle: the collection row, the connector connection (which connector, which
streams, which sync mode), the pointer to the encrypted configuration that
user-service stores for the owning user, and the syncs that fill it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from connector import (
    BaseSource,
    ConfiguredCatalog,
    DestinationSyncMode,
    Job,
    SyncMode,
    redact_secrets,
)
from localization import t

from core.exceptions import ApplicationError, ConflictError
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import (
    datasource_connection_repository,
    datasource_repository,
    schedule_repository,
)
from integrations import rag_client, user_service_client
from service.common.base import BaseService
from service.ingest import connector_catalog_service as catalog
from service.ingest.connector_runtime import ConnectorConfigMissingError, get_connector_runtime
from service.ingest.ingestion_service import is_graph_rag_available
from service.runtime.store_service import get_assistant_from_store, update_assistant_in_store

if TYPE_CHECKING:
    from infrastructure.db.repositories import (
        DatasourceConnectionRepository,
        DatasourceRepository,
        ScheduleRepository,
    )
    from service.ingest.connector_runtime import ConnectorRuntime

logger = get_logger(__name__)

#: Valid (sync mode, destination sync mode) pairs.
VALID_SYNC_COMBOS = {
    ("full_refresh", "overwrite"),
    ("full_refresh", "append"),
    ("incremental", "append"),
}
_LEGACY_SENSITIVE_KEYS = ("password", "api_key", "secret", "token", "credentials", "private_key")


def _truncate(text: str, limit: int = 500) -> str:
    return text[:limit] + "..." if len(text) > limit else text


def _epoch_seconds(value: datetime | None) -> int | None:
    return int(value.timestamp()) if value else None


def _redacted(text: str, source_class: type[BaseSource], config: dict[str, Any]) -> str:
    """``text`` without the secrets of ``config`` (whatever its state of validity), URL
    passwords and query strings: the connector's own view of its secrets when the
    configuration validates, the values under its secret field names otherwise."""
    try:
        secrets = source_class.from_config(config).secret_values()
    except Exception:  # an invalid configuration still has secrets to hide
        secrets = [str(config.get(name)) for name in source_class.secret_fields() if config.get(name)]
    return redact_secrets(text, secrets)


class _DiscoveryError(Exception):
    """A source could not be opened or read; ``detail`` is the redacted driver message.

    Raised by ``DatasourceService._discover`` and turned into the bad request of
    the operation that asked (create, update, preview) by its caller.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DatasourceService(BaseService):
    """Datasources, their connector connections, and their syncs.

    Collaborators are resolved lazily so a test can inject fakes:

    - ``ds_repo`` — the collection rows (``DatasourceRepository``)
    - ``connection_repo`` — ``datasource_connections``
    - ``schedule_repo`` — ``sync_schedules``
    - ``configs`` — the user-service connector-configuration client
    - ``runtime`` — the connector runtime (registry, runner, job history)
    """

    def __init__(
        self,
        ds_repo: DatasourceRepository | None = None,
        connection_repo: DatasourceConnectionRepository | None = None,
        schedule_repo: ScheduleRepository | None = None,
        configs: Any = None,
        runtime: ConnectorRuntime | None = None,
    ):
        self._ds_repo_override = ds_repo
        self._connection_repo_override = connection_repo
        self._schedule_repo_override = schedule_repo
        self._configs = configs or user_service_client
        self._runtime_override = runtime

    @property
    def _ds_repo(self) -> DatasourceRepository:
        return self._ds_repo_override or datasource_repository()

    @property
    def _connections(self) -> DatasourceConnectionRepository:
        return self._connection_repo_override or datasource_connection_repository()

    @property
    def _schedules(self) -> ScheduleRepository:
        return self._schedule_repo_override or schedule_repository()

    @property
    def _runtime(self) -> ConnectorRuntime:
        return self._runtime_override or get_connector_runtime()

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _require_collection(self, datasource_id: str) -> dict[str, Any]:
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            self._raise_not_found("datasource.not_found", datasource_id=datasource_id)
        return row

    def _source_class(self, connector_type: str) -> type[BaseSource]:
        try:
            return catalog.get_source_class(connector_type)
        except ValueError:
            self._raise_bad_request("datasource.unknown_connector", connector_type=connector_type)

    def _registered_connector_name(self, connector_type: str) -> str | None:
        """``connector_type`` as a connector this service can run, else ``None``.

        Collections created before the in-process connectors carry names like
        ``source-postgres``; those map onto the connector of the same family
        when one exists, so such a datasource can be given a configuration.
        """
        for candidate in (connector_type, connector_type.removeprefix("source-").replace("-", "_")):
            try:
                catalog.get_source_class(candidate)
            except ValueError:
                continue
            return candidate
        return None

    async def _discover(self, source_class: type[BaseSource], config: dict[str, Any]):
        """Open the source and read its catalog; a failing source raises ``_DiscoveryError``."""
        try:
            async with source_class.from_config(config) as source:
                return await source.discover()
        except ApplicationError:
            raise
        except Exception as exc:
            # Shown to people who only ever see masked secrets: a driver quoting its
            # address (key in the query, password in the DSN) must not undo that.
            raise _DiscoveryError(_redacted(str(exc), source_class, config)) from exc

    async def _stored_config(self, connection: dict[str, Any]) -> dict[str, Any] | None:
        stored = await self._configs.get_connector_config(connection["owner_user_id"], connection["config_id"])
        if not stored or not isinstance(stored.get("config"), dict):
            return None
        return stored["config"]

    @staticmethod
    def _mask_legacy_config(config: dict[str, Any]) -> dict[str, Any]:
        """Mask a configuration kept in collection metadata by an older version."""
        masked: dict[str, Any] = {}
        for key, value in (config or {}).items():
            if any(marker in key.lower() for marker in _LEGACY_SENSITIVE_KEYS):
                masked[key] = "****"
            elif isinstance(value, dict):
                masked[key] = DatasourceService._mask_legacy_config(value)
            else:
                masked[key] = value
        return masked

    def _schedule_summary(self, schedule: dict[str, Any] | None, update_graph_rag: bool) -> dict[str, Any] | None:
        if not schedule or not schedule.get("enabled"):
            return None
        return {
            "cron_expression": schedule["cron_expression"],
            "preset": schedule.get("preset", "custom"),
            "enabled": True,
            "update_graph_rag": update_graph_rag,
            "next_run_at": schedule.get("next_run_at")
            or self._schedules.next_run_iso(schedule["cron_expression"], schedule.get("timezone", "UTC")),
        }

    @staticmethod
    def _last_run(job: Job | None) -> tuple[str | None, str | None]:
        if job is None:
            return None, None
        stamp = job.finished_at or job.heartbeat_at or job.created_at
        return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z"), job.status.value

    # =========================================================================
    # DataSource CRUD
    # =========================================================================

    async def list_datasources(self) -> list[dict[str, Any]]:
        """List all configured data sources with their schedule summaries."""
        rows = await self._ds_repo.list_datasource_collections()
        if not rows:
            return []

        connections: dict[str, dict[str, Any]] = {}
        schedules: dict[str, dict[str, Any]] = {}
        try:
            connections = {c["datasource_id"]: c for c in await self._connections.list_all()}
            schedules = {s["datasource_id"]: s for s in await self._schedules.list_all()}
        except Exception:
            logger.warning("Could not load datasource connections or schedules", exc_info=True)

        # Collect ids that need a live rag-service count, then fetch concurrently.
        needs_count_ids = [
            # Same tolerant id read the result loop below uses: rows reach here
            # from more than one query shape.
            str(row.get("uuid") or row.get("id") or "")
            for row in rows
            if not (row.get("cmetadata", {}) or {}).get("chunk_stats", {}).get("chunk_count")
            and not row.get("doc_count")
            and (row.get("uuid") or row.get("id"))
        ]
        counts = (
            await asyncio.gather(*(self._ds_repo.count_embeddings(ds_id) for ds_id in needs_count_ids))
            if needs_count_ids
            else []
        )
        entity_counts = dict(zip(needs_count_ids, counts, strict=True))

        results = []
        for row in rows:
            meta = row.get("cmetadata", {}) or {}
            connector_type = meta.get("connector_type", "unknown")
            ds_id = str(row.get("uuid") or row.get("id") or "")
            chunk_stats = meta.get("chunk_stats", {}) if isinstance(meta, dict) else {}
            chunk_count = chunk_stats.get("chunk_count", 0) or row.get("doc_count", 0) or entity_counts.get(ds_id, 0)
            connection = connections.get(ds_id)
            update_graph_rag = bool(connection and connection.get("update_graph_rag"))

            results.append(
                {
                    "id": ds_id,
                    "name": row["name"],
                    "update_graph_rag": update_graph_rag,
                    "connector_type": connector_type,
                    "connector_display_name": catalog.format_connector_name(connector_type),
                    "streams": meta.get("streams"),
                    "sync_status": meta.get("sync_status"),
                    "sync_progress": meta.get("sync_progress"),
                    "document_count": chunk_count,
                    "created_at": meta.get("created_at"),
                    "last_synced_at": meta.get("last_synced_at"),
                    "schedule_summary": self._schedule_summary(schedules.get(ds_id), update_graph_rag),
                }
            )

        return results

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
        *,
        owner_user_id: str,
    ) -> dict[str, Any]:
        """Create a data source owned by ``owner_user_id``.

        1. Validate the configuration and discover the source's streams.
        2. Store the configuration, encrypted, in user-service.
        3. Create the collection and its connector connection.
        """
        if await self._ds_repo.get_collection_by_name(name):
            raise ConflictError(
                message=t("datasource.duplicate_name", name=name),
                message_key="datasource.duplicate_name",
                message_params={"name": name},
            )

        source_class = self._source_class(connector_type)
        try:
            config = catalog.validated_config(source_class, catalog.config_from_form(source_class, connector_config))
        except ValueError as exc:
            self._raise_bad_request(
                "datasource.create_source_failed", error=_redacted(str(exc), source_class, connector_config)
            )

        try:
            discovered = await self._discover(source_class, config)
        except _DiscoveryError as failure:
            self._raise_bad_request("datasource.create_connection_failed", error=failure.detail)
        configured = ConfiguredCatalog.from_catalog(discovered, only=streams or None)

        owner_id = user_service_client.connector_config_owner_id(owner_user_id)
        try:
            stored = await self._configs.create_connector_config(owner_id, connector_type, name, config)
            config_id = str(stored["id"])
        except Exception as exc:
            self._raise_internal_error("datasource.store_config_failed", error=str(exc))

        collection_uuid = str(uuid4())
        now = datetime.now(UTC).isoformat()
        meta = {
            "connector_type": connector_type,
            "streams": streams,
            "content_fields": content_fields,
            "created_at": now,
            "friendly_name": name,
        }
        try:
            row = await self._ds_repo.create_collection(collection_uuid=collection_uuid, name=name, cmetadata=meta)
            if not row:
                raise RuntimeError("collection insert returned no row")
            await self._connections.create(
                datasource_id=collection_uuid,
                connector_name=connector_type,
                config_id=config_id,
                owner_user_id=owner_id,
                catalog=configured.model_dump(mode="json"),
            )
        except Exception as exc:
            await self._discard(owner_id, config_id, collection_uuid)
            if "UniqueViolation" in str(exc) or "duplicate key" in str(exc).lower():
                raise ConflictError(
                    message=t("datasource.duplicate_name", name=name),
                    message_key="datasource.duplicate_name",
                    message_params={"name": name},
                ) from exc
            self._raise_internal_error("datasource.create_collection_failed")

        await self._attach_to_rag_assistant(collection_uuid)

        return {
            "id": collection_uuid,
            "name": name,
            "connector_type": connector_type,
            "connector_display_name": catalog.format_connector_name(connector_type),
            "streams": streams,
            "created_at": now,
        }

    async def _discard(self, owner_id: str, config_id: str, collection_uuid: str) -> None:
        """Best-effort cleanup of a half-created datasource."""
        for cleanup in (
            self._ds_repo.delete_collection(collection_uuid),
            self._configs.delete_connector_config(owner_id, config_id),
        ):
            try:
                await cleanup
            except Exception:
                logger.warning("Cleanup after a failed datasource create did not complete", exc_info=True)

    @staticmethod
    async def _attach_to_rag_assistant(datasource_id: str) -> None:
        """Make a new datasource searchable by the built-in RAG assistant."""
        try:
            assistant = await get_assistant_from_store("rag-assistant")
            if not assistant:
                return
            config = assistant.get("config", {})
            collections = config.setdefault("rag_config", {}).setdefault("collections", [])
            if datasource_id not in collections:
                collections.append(datasource_id)
                await update_assistant_in_store("rag-assistant", {"config": config})
                logger.info("Attached datasource %s to rag-assistant", datasource_id)
        except Exception as exc:
            logger.error("Failed to auto-attach datasource: %s", exc)

    async def update_datasource(
        self,
        datasource_id: str,
        name: str | None = None,
        connector_config: dict[str, Any] | None = None,
        streams: list[str] | None = None,
        sync_mode: str | None = None,
        destination_sync_mode: str | None = None,
        *,
        acting_user_id: str | None = None,
        include_error_detail: bool = True,
    ) -> dict[str, Any]:
        """Update a data source's name, configuration, streams, and/or sync mode."""
        row = await self._require_collection(datasource_id)
        meta = row.get("cmetadata", {}) or {}

        if sync_mode is not None or destination_sync_mode is not None:
            sm = sync_mode or "full_refresh"
            dm = destination_sync_mode or "overwrite"
            if (sm, dm) not in VALID_SYNC_COMBOS:
                self._raise_bad_request("datasource.invalid_sync_mode_combination", sync_mode=sm, dest_mode=dm)

        connection = await self._connections.get(datasource_id)
        connector_name = (
            connection["connector_name"]
            if connection
            else self._registered_connector_name(str(meta.get("connector_type") or ""))
        )
        if connector_name is None or (connection is None and connector_config is None):
            self._raise_bad_request("datasource.no_connection")
        source_class = self._source_class(connector_name)

        # ---- configuration ------------------------------------------------
        effective_config: dict[str, Any] | None = None
        stored: dict[str, Any] | None = None
        config_is_gone = False
        if connector_config is not None:
            stored = (await self._stored_config(connection)) if connection else None
            # "Save the configuration again": the row user-service kept for this
            # connection no longer exists, so there is nothing to update in place.
            config_is_gone = connection is not None and stored is None
            try:
                submitted = catalog.config_from_form(source_class, connector_config)
                effective_config = catalog.validated_config(
                    source_class, catalog.merge_kept_secrets(source_class, submitted, stored or {})
                )
            except ValueError as exc:
                self._raise_bad_request(
                    "datasource.update_source_failed", error=_redacted(str(exc), source_class, connector_config)
                )

        # ---- stream catalog -----------------------------------------------
        current = ConfiguredCatalog.model_validate(connection["catalog"]) if connection else ConfiguredCatalog()
        configured = current
        rediscover = streams is not None or connection is None
        if rediscover:
            config = effective_config or (await self._stored_config(connection) if connection else None)
            if config is None:
                self._raise_bad_request("datasource.config_missing")
            try:
                discovered = await self._discover(source_class, config)
            except _DiscoveryError as failure:
                self._raise_bad_request("datasource.update_streams_failed", error=failure.detail)
            wanted = streams if streams is not None else (meta.get("streams") or None)
            configured = ConfiguredCatalog.from_catalog(discovered, only=wanted or None)
            for stream in configured.streams:
                previous = next((s for s in current.streams if s.stream.name == stream.stream.name), None)
                if previous is not None:
                    stream.sync_mode = previous.sync_mode
                    stream.destination_sync_mode = previous.destination_sync_mode
        if sync_mode is not None or destination_sync_mode is not None:
            wanted_mode = SyncMode(sync_mode or "full_refresh")
            for stream in configured.streams:
                supported = wanted_mode in stream.stream.supported_sync_modes
                stream.sync_mode = wanted_mode if supported else SyncMode.FULL_REFRESH
                stream.destination_sync_mode = DestinationSyncMode(destination_sync_mode or "overwrite")

        # ---- persist ------------------------------------------------------
        try:
            if connection is None:
                owner_id = user_service_client.connector_config_owner_id(acting_user_id or "")
                stored_meta = await self._configs.create_connector_config(
                    owner_id, connector_name, name or row["name"], effective_config
                )
                await self._connections.create(
                    datasource_id=datasource_id,
                    connector_name=connector_name,
                    config_id=str(stored_meta["id"]),
                    owner_user_id=owner_id,
                    catalog=configured.model_dump(mode="json"),
                )
            else:
                changes: dict[str, Any] = {}
                if config_is_gone:
                    # Stored anew for the same owner; the connection follows it.
                    stored_meta = await self._configs.create_connector_config(
                        connection["owner_user_id"], connector_name, name or row["name"], effective_config
                    )
                    changes["config_id"] = str(stored_meta["id"])
                elif effective_config is not None or name is not None:
                    await self._configs.update_connector_config(
                        connection["owner_user_id"],
                        connection["config_id"],
                        name=name,
                        config=effective_config,
                    )
                if configured is not current or sync_mode is not None or destination_sync_mode is not None:
                    changes["catalog"] = configured.model_dump(mode="json")
                if changes:
                    await self._connections.update(datasource_id, **changes)
        except ApplicationError as exc:
            self._raise_bad_request("datasource.update_source_failed", error=exc.message)

        if connection is not None and effective_config is not None and effective_config != stored:
            # A connection pointed elsewhere must not skip the rows its old cursor
            # says it has seen: the next sync reads every stream from the start.
            await self._runtime.reset_checkpoints(datasource_id)

        updated = False
        if name is not None:
            meta["friendly_name"] = name
            updated = True
        if "connector_config" in meta:
            # Configurations are never kept in collection metadata; drop what an
            # older version left behind.
            del meta["connector_config"]
            updated = True
        if streams is not None:
            meta["streams"] = streams
            updated = True
        if meta.get("connector_type") != connector_name:
            meta["connector_type"] = connector_name
            updated = True

        await self._ds_repo.update_collection(
            datasource_id,
            name=name if name is not None else None,
            cmetadata=meta if updated else None,
        )

        return await self.get_datasource_details(datasource_id, include_error_detail=include_error_detail)

    async def delete_datasource(self, datasource_id: str) -> dict[str, Any]:
        """Delete a data source: its chunks in rag-service, then its collection record,
        connection and stored configuration.

        rag-service drops the Milvus table while the collection row still names it.
        When that call fails, nothing is deleted and its error is the answer, so the
        delete can be repeated once rag-service is back.
        """
        await self._require_collection(datasource_id)

        active_job = self._runtime.runner.active_job_id(datasource_id)
        if active_job:
            await self._runtime.runner.cancel(active_job)

        await self._delete_rag_records(datasource_id)

        connection = await self._connections.get(datasource_id)
        if connection:
            try:
                await self._configs.delete_connector_config(connection["owner_user_id"], connection["config_id"])
            except Exception:
                logger.warning("Could not delete the stored configuration of datasource %s", datasource_id)
            await self._connections.delete(datasource_id)

        # Schedules, jobs and checkpoints go with the collection (ON DELETE CASCADE).
        await self._ds_repo.delete_collection(datasource_id)
        logger.info("Deleted datasource %s", datasource_id)
        return {"status": "deleted", "id": datasource_id}

    @staticmethod
    async def _delete_rag_records(datasource_id: str) -> None:
        """Have rag-service drop what it stores for the datasource.

        A 404 means rag-service does not know the collection (nothing was ever
        written under this id, or it is gone already): there is nothing to remove.
        Any other failure propagates before anything of the datasource is deleted.
        """
        try:
            result = await rag_client.delete_datasource_records(datasource_id)
        except ApplicationError as error:
            if error.status_code != 404:
                raise
            logger.info("rag-service holds nothing for datasource %s", datasource_id)
            return
        logger.info(
            "Removed %s chunks of datasource %s from rag-service",
            result.get("chunks_removed", "?"),
            datasource_id,
        )

    async def get_datasource_details(
        self,
        datasource_id: str,
        page: int = 1,
        page_size: int = 10,
        *,
        include_config: bool = True,
        include_error_detail: bool = True,
    ) -> dict[str, Any]:
        """Get detailed information about a data source with paginated chunks.

        ``include_config=False`` leaves the connection settings out (``config``
        is empty): hosts, account names and the like are for callers who may
        edit the connection, and are then not even fetched.
        ``include_error_detail=False`` says that the last sync failed, not why.
        """
        row = await self._require_collection(datasource_id)
        col_meta = row.get("cmetadata", {}) or {}
        connector_type = col_meta.get("connector_type", "unknown")

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        # Pre-computed chunk stats are written as batches are indexed; before the
        # first sync there are none and rag-service is asked for the live count.
        chunk_stats = col_meta.get("chunk_stats", {}) or {}
        chunk_count = chunk_stats.get("chunk_count", 0) or await self._ds_repo.count_embeddings(datasource_id)
        avg_chars = chunk_stats.get("avg_chunk_chars", 0)
        avg_tokens = chunk_stats.get("avg_chunk_tokens", 0)

        emb_rows = await self._ds_repo.get_paginated_embeddings(datasource_id, limit=page_size, offset=offset)
        chunks, samples = [], []
        for emb in emb_rows:
            doc_text = emb["document"] or ""
            emb_meta = emb.get("cmetadata", {}) or {}
            chunks.append(
                {
                    "content": _truncate(doc_text),
                    "char_count": emb_meta.get("char_count", len(doc_text)),
                    "token_count": emb_meta.get("token_count", max(len(doc_text.split()), int(len(doc_text) / 4))),
                    "word_count": emb_meta.get("word_count", len(doc_text.split())),
                    "source": emb_meta.get("source"),
                    "stream": emb_meta.get("stream"),
                    "connector_type": emb_meta.get("connector_type"),
                    "metadata": emb_meta,
                }
            )
            samples.append({"content": _truncate(doc_text), "metadata": emb_meta})

        connection = await self._connections.get(datasource_id)
        masked_config: dict[str, Any] = {}
        sync_mode_val = dest_sync_mode_val = None
        schedule_data = None
        if connection:
            if include_config:
                try:
                    stored = await self._stored_config(connection)
                    if stored is not None:
                        masked_config = catalog.config_to_form(self._source_class(connection["connector_name"]), stored)
                except Exception as exc:
                    logger.warning("Could not read the stored configuration of %s: %s", datasource_id, exc)

            configured = ConfiguredCatalog.model_validate(connection["catalog"])
            if configured.streams:
                sync_mode_val = configured.streams[0].sync_mode.value
                dest_sync_mode_val = configured.streams[0].destination_sync_mode.value

            schedule_data = await self._schedule_details(datasource_id, connection)
        elif include_config and col_meta.get("connector_config"):
            masked_config = self._mask_legacy_config(col_meta["connector_config"])

        return {
            "id": str(row["uuid"]),
            "name": row["name"],
            "connector_type": connector_type,
            "connector_display_name": catalog.format_connector_name(connector_type),
            "config": masked_config,
            "streams": col_meta.get("streams"),
            "sync_status": col_meta.get("sync_status"),
            "sync_progress": col_meta.get("sync_progress"),
            "document_count": chunk_count,
            "chunk_count": chunk_count,
            "chunks": chunks,
            "avg_chunk_tokens": avg_tokens or None,
            "avg_chunk_chars": avg_chars or None,
            "sample_documents": samples,
            "created_at": col_meta.get("created_at"),
            "last_synced_at": col_meta.get("last_synced_at"),
            "last_error": self._error_text(col_meta.get("last_error"), include_error_detail),
            "sync_mode": sync_mode_val,
            "destination_sync_mode": dest_sync_mode_val,
            "schedule": schedule_data,
            "graph_rag_available": await is_graph_rag_available(),
        }

    async def _schedule_details(self, datasource_id: str, connection: dict[str, Any]) -> dict[str, Any] | None:
        try:
            schedule = await self._schedules.get_by_datasource(datasource_id)
            if not schedule or not schedule.get("enabled"):
                return None
            last_run_at, last_run_status = self._last_run(await self._runtime.latest_job(datasource_id))
            now = datetime.now(UTC).isoformat()
            return {
                "id": datasource_id,
                "datasource_id": datasource_id,
                "cron_expression": schedule["cron_expression"],
                "preset": schedule.get("preset", "custom"),
                "enabled": True,
                "update_graph_rag": bool(connection.get("update_graph_rag")),
                "timezone": schedule.get("timezone", "UTC"),
                "next_run_at": schedule.get("next_run_at"),
                "last_run_at": last_run_at,
                "last_run_status": last_run_status,
                "created_at": schedule.get("created_at") or now,
                "updated_at": schedule.get("updated_at") or now,
            }
        except Exception:
            logger.debug("Could not load the schedule of %s", datasource_id, exc_info=True)
            return None

    # =========================================================================
    # Sync operations
    # =========================================================================

    async def trigger_sync(
        self, datasource_id: str, triggered_by: str = "manual", *, full_refresh: bool = False
    ) -> dict[str, Any]:
        """Start a sync of a data source in the background.

        ``full_refresh`` forgets the saved incremental checkpoints and reads every
        stream from the start.
        """
        await self._require_collection(datasource_id)
        if not await self._connections.get(datasource_id):
            self._raise_bad_request("datasource.no_connection")

        # The job that gets created marks the datasource "starting": a trigger refused
        # because a sync is running must leave that sync's progress alone.
        try:
            job = await self._runtime.start_sync(datasource_id, full_refresh=full_refresh)
        except ConnectorConfigMissingError as exc:
            await self._mark_sync_failed(datasource_id, str(exc))
            self._raise_bad_request("datasource.config_missing")
        except Exception as exc:
            # A sync that could not even begin is reported like one that failed. The
            # text is kept for everyone who may read the datasource: no credentials in it.
            await self._mark_sync_failed(datasource_id, redact_secrets(str(exc)))
            raise

        if job is None:
            return {"status": "Already syncing or queued", "id": datasource_id}
        logger.info(
            "Sync %s of datasource %s started (%s%s)",
            job.id,
            datasource_id,
            triggered_by,
            ", full refresh" if full_refresh else "",
        )
        return {"status": "Sync started", "id": datasource_id}

    async def _mark_sync_failed(self, datasource_id: str, error: str) -> None:
        row = await self._ds_repo.get_collection(datasource_id)
        if not row:
            return
        meta = row.get("cmetadata", {}) or {}
        meta.update(sync_status="error", sync_progress=0, last_error=error)
        await self._ds_repo.update_collection_metadata(datasource_id, meta)

    @staticmethod
    def _error_text(error: str | None, include_detail: bool) -> str | None:
        """The reason of a failed sync as the caller may read it.

        The text names hosts, accounts and what the remote system answered. That
        is for callers who may run a sync; the others learn that it failed.
        """
        if not error or include_detail:
            return error
        return t("datasource.sync_error_hidden")

    async def get_sync_status(self, datasource_id: str, *, include_error_detail: bool = True) -> dict[str, Any]:
        """Get current sync status for real-time progress tracking."""
        row = await self._require_collection(datasource_id)
        meta = row.get("cmetadata", {}) or {}

        schedule_info = None
        try:
            connection = await self._connections.get(datasource_id)
            summary = self._schedule_summary(
                await self._schedules.get_by_datasource(datasource_id),
                bool(connection and connection.get("update_graph_rag")),
            )
            if summary:
                schedule_info = {
                    key: summary[key] for key in ("enabled", "cron_expression", "next_run_at", "update_graph_rag")
                }
        except Exception:
            logger.debug("Could not load the schedule of %s", datasource_id, exc_info=True)

        return {
            "id": datasource_id,
            "sync_status": meta.get("sync_status", "idle"),
            "sync_progress": meta.get("sync_progress", 0),
            "last_synced_at": meta.get("last_synced_at"),
            "last_error": self._error_text(meta.get("last_error"), include_error_detail),
            "graph_update_status": meta.get("graph_update_status"),
            "queue_position": await self._runtime.queue_position(datasource_id),
            "is_active": await self._runtime.is_active(datasource_id),
            "schedule": schedule_info,
        }

    async def get_sync_history(
        self, datasource_id: str, limit: int = 20, *, include_error_detail: bool = True
    ) -> list[dict[str, Any]]:
        """Recent sync jobs of a data source, newest first."""
        await self._require_collection(datasource_id)
        history = []
        for job in await self._runtime.jobs.list(datasource_id, limit=limit):
            ended = job.finished_at or job.heartbeat_at
            started = job.started_at or job.created_at
            history.append(
                {
                    "id": job.id,
                    "status": job.status.value,
                    "created_at": _epoch_seconds(job.created_at),
                    "updated_at": _epoch_seconds(ended or job.created_at),
                    "duration_seconds": int((ended - started).total_seconds()) if ended else None,
                    "bytes_synced": 0,
                    "records_synced": job.records_read,
                    "error_message": self._error_text(job.error, include_error_detail),
                }
            )
        return history

    async def source_preview(self, datasource_id: str) -> dict[str, Any]:
        """Live stream schemas of a data source's connector."""
        row = await self._require_collection(datasource_id)
        connection = await self._connections.get(datasource_id)
        if not connection:
            self._raise_not_found("datasource.no_connection")
        config = await self._stored_config(connection)
        if config is None:
            self._raise_not_found("datasource.config_missing")

        source_class = self._source_class(connection["connector_name"])
        try:
            discovered = await self._discover(source_class, config)
        except _DiscoveryError as failure:
            self._raise_bad_request("datasource.update_streams_failed", error=failure.detail)
        return {
            "datasource_id": datasource_id,
            "source_name": row.get("name", ""),
            "connector_type": connection["connector_name"],
            "streams": [
                {
                    "name": stream.name,
                    "key_properties": stream.source_defined_primary_key,
                    # Most API connectors declare no schema; that is "unknown", not "no fields".
                    "field_count": len((stream.json_schema or {}).get("properties") or {}) or None,
                    "schema": stream.json_schema,
                }
                for stream in discovered.streams
            ],
            "note": "This is live schema from the source. Actual data is only stored as embeddings.",
        }


# Singleton instance
_datasource_service: DatasourceService | None = None


def get_datasource_service() -> DatasourceService:
    """Get the singleton DatasourceService instance."""
    global _datasource_service
    if _datasource_service is None:
        _datasource_service = DatasourceService()
    return _datasource_service
