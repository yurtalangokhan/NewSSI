"""
Airbyte Connector Management Module.

Thin API proxy that delegates all connector management to the Airbyte OSS
platform via the REST API.  **Zero** PyAirbyte, **zero** Docker-in-Docker,
**zero** flatten/reconstruct logic.

The raw JSON Schema spec is returned directly to the frontend, which renders
it natively via the recursive SchemaForm component.
"""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)
import logging as _stdlib_logging

logger_stdlib = _stdlib_logging.getLogger(__name__)
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from langchain_core.documents import Document

from service.AirbyteApiClientService import get_airbyte_client
from service.AirbyteDestinationService import get_destination_reader
from service.Schemas import ConnectorInfo, ConnectorSpec

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Display name helper
# ---------------------------------------------------------------------------


_SPECIAL_NAMES: dict[str, str] = {
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb-v2": "MongoDB",
    "mssql": "Microsoft SQL Server",
    "gcs": "Google Cloud Storage",
    "s3": "Amazon S3",
    "google-analytics-v4": "Google Analytics (UA)",
    "google-analytics-data-api": "Google Analytics 4",
}


def _format_connector_name(connector_name: str) -> str:
    """Convert connector name to human-readable format."""
    short = connector_name.replace("source-", "")
    if short in _SPECIAL_NAMES:
        return _SPECIAL_NAMES[short]
    return short.replace("-", " ").title()


def _infer_category(definition: dict[str, Any]) -> str:
    """Best-effort category inference from Airbyte source definition."""
    source_type = definition.get("sourceType", "")
    if source_type:
        return source_type
    repo = definition.get("dockerRepository", "")
    if "database" in repo or any(
        db in repo for db in ["postgres", "mysql", "mssql", "mongo", "oracle", "mariadb"]
    ):
        return "database"
    if "file" in repo or "s3" in repo or "gcs" in repo:
        return "file"
    return "api"


# ---------------------------------------------------------------------------
# Connector discovery (replaces PyAirbyte get_available_connectors)
# ---------------------------------------------------------------------------


async def discover_connectors() -> list[ConnectorInfo]:
    """List all available Airbyte source connectors from the platform."""
    client = get_airbyte_client()
    definitions = await client.list_source_definitions()

    results: list[ConnectorInfo] = []
    for defn in definitions:
        name = defn.get("name", "")
        docker_repo = defn.get("dockerRepository", "")
        short_name = docker_repo.split("/")[-1] if "/" in docker_repo else docker_repo

        results.append(
            ConnectorInfo(
                name=short_name or name,
                display_name=name or _format_connector_name(short_name),
                source_definition_id=defn["sourceDefinitionId"],
                category=_infer_category(defn),
                icon_url=defn.get("icon"),
                documentation_url=defn.get("documentationUrl"),
            )
        )

    logger.info("Discovered %d connectors from Airbyte OSS", len(results))
    return results


async def get_connectors_by_category() -> dict[str, list[ConnectorInfo]]:
    """Get connectors organized by category."""
    connectors = await discover_connectors()
    by_cat: dict[str, list[ConnectorInfo]] = {}
    for c in connectors:
        cat = c.category or "other"
        by_cat.setdefault(cat, []).append(c)
    return by_cat


async def get_connector_categories() -> list[str]:
    """Get sorted list of unique categories."""
    by_cat = await get_connectors_by_category()
    cats = sorted(by_cat.keys())
    for tail in ("unknown", "other"):
        if tail in cats:
            cats.remove(tail)
            cats.append(tail)
    return cats


async def get_category_labels() -> dict[str, str]:
    """Return category -> display label mapping."""
    labels = {
        "api": "API",
        "database": "Database",
        "file": "File",
        "custom": "Custom",
        "unknown": "Other",
        "other": "Other",
    }
    cats = await get_connector_categories()
    return {cat: labels.get(cat, cat.title()) for cat in cats}


async def search_connectors(query: str) -> list[ConnectorInfo]:
    """Search connectors by name."""
    connectors = await discover_connectors()
    q = query.lower()
    return [c for c in connectors if q in c.name.lower() or q in c.display_name.lower()]


async def find_connector_by_name(connector_name: str) -> ConnectorInfo | None:
    """Find a connector by its short name (e.g. 'source-postgres')."""
    connectors = await discover_connectors()
    for c in connectors:
        if c.name == connector_name:
            return c
    return None


# ---------------------------------------------------------------------------
# Connector spec (returns RAW JSON Schema — zero transformation)
# ---------------------------------------------------------------------------


async def get_connector_spec(connector_name: str) -> ConnectorSpec:
    """Get the configuration specification for a connector.

    Returns the **raw** JSON Schema ``connectionSpecification`` from
    the Airbyte API.  **NO** flattening, **NO** transformation.
    The frontend renders it natively via the recursive SchemaForm.
    """
    connector = await find_connector_by_name(connector_name)
    if not connector:
        raise ValueError(f"Connector not found: {connector_name}")

    client = get_airbyte_client()
    spec_data = await client.get_source_definition_spec(connector.source_definition_id)

    connection_spec = spec_data.get("connectionSpecification", {})

    return ConnectorSpec(
        name=connector_name,
        source_definition_id=connector.source_definition_id,
        connection_specification=connection_spec,
        documentation_url=spec_data.get("documentationUrl") or connector.documentation_url,
    )


# ---------------------------------------------------------------------------
# Connection testing
# ---------------------------------------------------------------------------


async def validate_connector_config(
    connector_name: str,
    config: dict[str, Any],
) -> bool:
    """Validate connector config by creating a temp source and testing.

    ``config`` is the **native nested** JSON structure produced directly
    by the SchemaForm — **NO** reconstruction needed.

    Returns True if valid, raises ValueError otherwise.
    """
    connector = await find_connector_by_name(connector_name)
    if not connector:
        raise ValueError(f"Connector not found: {connector_name}")

    client = get_airbyte_client()

    source = await client.create_source(
        name=f"_test_{connector_name}",
        source_definition_id=connector.source_definition_id,
        config=config,
    )
    source_id = source["sourceId"]

    try:
        result = await client.check_source_connection(source_id)
        status = result.get("status", "failed")
        if status == "succeeded":
            return True
        else:
            message = result.get("message", "Connection check failed")
            raise ValueError(f"Connection check failed: {message}")
    finally:
        try:
            await client.delete_source(source_id)
        except Exception:
            logger.warning("Could not delete temp source %s", source_id)


# ---------------------------------------------------------------------------
# Stream discovery
# ---------------------------------------------------------------------------


async def get_available_streams(
    connector_name: str,
    config: dict[str, Any],
) -> list[str]:
    """Discover available streams for a connector with given config."""
    connector = await find_connector_by_name(connector_name)
    if not connector:
        raise ValueError(f"Connector not found: {connector_name}")

    client = get_airbyte_client()

    source = await client.create_source(
        name=f"_discover_{connector_name}",
        source_definition_id=connector.source_definition_id,
        config=config,
    )
    source_id = source["sourceId"]

    try:
        schema = await client.discover_source_schema(source_id)
        catalog = schema.get("catalog", {})
        streams = catalog.get("streams", [])
        return [
            s.get("stream", {}).get("name", "") for s in streams if s.get("stream", {}).get("name")
        ]
    finally:
        try:
            await client.delete_source(source_id)
        except Exception:
            logger.warning("Could not delete temp source %s", source_id)


# ---------------------------------------------------------------------------
# Data extraction (via Airbyte sync -> destination reader)
# ---------------------------------------------------------------------------


def _sanitize_metadata_value(value: Any) -> Any:
    """Convert non-JSON-serializable values to safe types."""
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


def records_to_documents(
    records: list[dict[str, Any]],
    connector_name: str,
    content_fields: list[str] | None = None,
) -> list[Document]:
    """Convert raw records to LangChain Documents.

    This logic is extracted so both the sync listener and manual sync
    paths can reuse it.  It is identical to the old extract_documents()
    conversion logic.
    """
    documents: list[Document] = []

    for record in records:
        stream_name = record.pop("_stream", "unknown")

        if content_fields:
            content_parts = [
                f"{f}: {record[f]}" for f in content_fields if f in record and record[f]
            ]
            content = "\n".join(content_parts)
        else:
            PRIORITY_FIELDS = ["title", "name", "subject", "heading"]
            CONTENT_FIELDS = [
                "content",
                "text",
                "body",
                "description",
                "summary",
                "abstract",
                "message",
            ]
            EXCLUDE_FIELDS = {
                "_id",
                "created_at",
                "updated_at",
                "source",
                "tags",
                "category",
                "id",
                "uuid",
                "_ab_cdc_cursor",
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
                    if v is not None and not k.startswith("_") and k.lower() not in EXCLUDE_FIELDS
                ]
            content = "\n".join(content_parts)

        if not content.strip():
            continue

        doc_metadata: dict[str, Any] = {
            "source": f"airbyte:{connector_name}",
            "stream": stream_name,
            "connector_type": connector_name,
        }
        for k, v in record.items():
            if v is not None and not k.startswith("_"):
                doc_metadata[k] = _sanitize_metadata_value(v)

        documents.append(Document(page_content=content, metadata=doc_metadata))

    return documents


async def extract_documents_async(
    connector_name: str,
    config: dict[str, Any],
    streams: list[str] | None = None,
    content_fields: list[str] | None = None,
    source_id: str | None = None,
    connection_id: str | None = None,
    job_id: int | None = None,
) -> list[Document]:
    """Extract data via Airbyte sync and convert to LangChain Documents.

    If ``job_id`` is provided together with ``connection_id``, the output
    of an **already-completed** job is read directly — no new sync is
    triggered.  This is the path used by ``AirbyteSyncListener`` to avoid
    an infinite trigger loop.

    If only ``connection_id`` is provided (no ``job_id``), a new sync is
    triggered on the existing connection.  Otherwise creates a temporary
    source + connection, syncs, reads, and cleans up.
    """
    client = get_airbyte_client()
    reader = get_destination_reader()

    temp_source_id: str | None = None
    temp_connection_id: str | None = None
    # True when the caller already knows the job completed (listener path).
    _job_already_complete = False

    try:
        if connection_id and job_id:
            # Job already completed (called from AirbyteSyncListener) –
            # skip straight to reading the output.
            _job_already_complete = True
            logger.info(
                "Reading output from already-completed Airbyte job %d "
                "(connection %s) — no new sync triggered",
                job_id,
                connection_id,
            )
        elif connection_id:
            job_data = await client.trigger_sync(connection_id)
            job_id = job_data.get("job", {}).get("id")
        else:
            connector = await find_connector_by_name(connector_name)
            if not connector:
                raise ValueError(f"Connector not found: {connector_name}")

            source = await client.create_source(
                name=f"_extract_{connector_name}",
                source_definition_id=connector.source_definition_id,
                config=config,
            )
            temp_source_id = source["sourceId"]

            dest_id = await client.get_or_create_default_destination()

            schema = await client.discover_source_schema(temp_source_id)
            catalog = schema.get("catalog", {})
            catalog_streams = catalog.get("streams", [])

            if streams:
                catalog_streams = [
                    s for s in catalog_streams if s.get("stream", {}).get("name") in streams
                ]

            for cs in catalog_streams:
                cs["config"] = {
                    "syncMode": "full_refresh",
                    "destinationSyncMode": "overwrite",
                    "selected": True,
                }

            conn = await client.create_connection(
                source_id=temp_source_id,
                destination_id=dest_id,
                streams=catalog_streams,
            )
            temp_connection_id = conn["connectionId"]

            job_data = await client.trigger_sync(temp_connection_id)
            job_id = job_data.get("job", {}).get("id")

        if not job_id:
            raise ValueError("No job ID returned from sync trigger")

        # If the caller already knows the job succeeded (AirbyteSyncListener
        # path), skip the expensive poll-until-complete loop.
        if _job_already_complete:
            # We were given an existing job_id — it's already complete.
            result = await client.get_job(job_id)
        else:
            result = await client.poll_job_until_complete(job_id)
        job_info = result.get("job", result)
        job_status = job_info.get("status", "unknown")

        if job_status != "succeeded":
            # Try to extract detailed failure reason from job attempts
            failure_detail = ""
            try:
                attempts = result.get("attempts", [])
                if attempts:
                    last_attempt = attempts[-1].get("attempt", {})
                    failure_summary = last_attempt.get("failureSummary", {})
                    failures = failure_summary.get("failures", [])
                    if failures:
                        messages = [
                            f.get("failureOrigin", "")
                            + ": "
                            + f.get("externalMessage", f.get("internalMessage", ""))
                            for f in failures
                        ]
                        failure_detail = "; ".join(m for m in messages if m.strip(" :"))
                    if not failure_detail:
                        # Fallback: check for stderr output in logs
                        logs = last_attempt.get("logs", {}).get("logLines", [])
                        error_lines = [
                            l
                            for l in logs
                            if isinstance(l, str)
                            and ("error" in l.lower() or "exception" in l.lower())
                        ]
                        if error_lines:
                            failure_detail = error_lines[-1][:500]
            except Exception:
                pass
            error_msg = f"Airbyte sync job failed with status: {job_status}"
            if failure_detail:
                error_msg += f" — {failure_detail}"
            raise ValueError(error_msg)

        records = await reader.read_sync_output(
            connection_id=connection_id or temp_connection_id,
            job_id=job_id,
        )

        documents = records_to_documents(records, connector_name, content_fields)

        await reader.cleanup_sync_output(
            connection_id=connection_id or temp_connection_id,
            job_id=job_id,
        )

        logger.info(
            "Extracted %d documents from %s via Airbyte sync",
            len(documents),
            connector_name,
        )
        return documents

    finally:
        if temp_connection_id:
            try:
                await client.delete_connection(temp_connection_id)
            except Exception:
                logger.warning("Could not delete temp connection %s", temp_connection_id)
        if temp_source_id:
            try:
                await client.delete_source(temp_source_id)
            except Exception:
                logger.warning("Could not delete temp source %s", temp_source_id)
