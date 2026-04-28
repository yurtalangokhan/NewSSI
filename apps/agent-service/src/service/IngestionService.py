"""
Data Ingestion Module.

This module handles the background ingestion of data from Airbyte sources
into the vector store for RAG operations.
"""
import asyncio
import logging
import os
import time
from datetime import UTC, datetime

import httpx

from core.db import AirbyteMappingRepository, DatasourceRepository

# LangConnect base URL for Graph RAG rebuild requests
LANGCONNECT_BASE_URL = os.environ.get("RAG_SERVICE_API_URL", "http://langconnect-api:8083")
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


async def run_ingestion(
    datasource_id: str,
    update_graph_rag: bool = False,
    job_id: int | None = None,
):
    """
    Trigger an Airbyte sync for a datasource.

    With the streaming architecture, the custom ``destination-embedding``
    connector POSTs record batches directly to ``/ingest/batch`` during
    the sync.  Embedding happens *during* sync — not after.

    This function only needs to:
    1. Set initial sync status
    2. Trigger the Airbyte sync via API
    3. Poll until the sync job completes (destination-embedding handles data)
    4. The ``/ingest/batch`` endpoint marks completion on the last batch

    If ``job_id`` is provided the sync already completed (listener path) —
    the destination-embedding already sent all batches, so we just verify.
    """
    logger.info(f"Starting ingestion for datasource {datasource_id}")

    try:
        ds_repo = DatasourceRepository()
        mapping_repo = AirbyteMappingRepository()

        # 1. Fetch configuration
        row = await ds_repo.get_collection(datasource_id)
        if not row:
            logger.error(f"Datasource {datasource_id} not found")
            return
        config = row.get("cmetadata", {})

        connector_type = config.get("connector_type")
        if not connector_type:
            await update_sync_status(datasource_id, "error", "Missing connector_type")
            return

        # 2. If job_id is provided, the sync already completed and
        #    destination-embedding already streamed all batches to /ingest/batch.
        #    Just update the mapping watermark — nothing else to do.
        if job_id:
            logger.info(
                "Job %d already completed for %s — destination-embedding "
                "handled all batches during sync",
                job_id, datasource_id,
            )
            # Optionally trigger Graph RAG rebuild
            if update_graph_rag:
                await _trigger_graph_rag_rebuild(datasource_id)
            return

        # 3. Manual sync trigger — kick off Airbyte sync, destination-embedding
        #    will POST batches to /ingest/batch as records flow.
        await update_sync_progress(datasource_id, "syncing", 5)

        connection_id = None
        try:
            mapping = await mapping_repo.get(datasource_id)
            if mapping:
                connection_id = mapping["airbyte_connection_id"]
        except Exception:
            pass

        if not connection_id:
            await update_sync_status(datasource_id, "error", "No Airbyte connection found")
            return

        from service.AirbyteApiClientService import get_airbyte_client
        client = get_airbyte_client()

        # Trigger the sync — destination-embedding streams batches in real-time
        job_data = await client.trigger_sync(connection_id)
        new_job_id = job_data.get("job", {}).get("id")
        if not new_job_id:
            await update_sync_status(datasource_id, "error", "No job ID returned")
            return

        logger.info("Airbyte sync job %d triggered for %s", new_job_id, datasource_id)
        await update_sync_progress(datasource_id, "syncing", 10)

        # 4. Poll until sync completes (embedding happens during sync via /ingest/batch)
        result = await client.poll_job_until_complete(new_job_id)
        job_info = result.get("job", result)
        job_status = job_info.get("status", "unknown")

        if job_status != "succeeded":
            failure_detail = ""
            try:
                attempts = result.get("attempts", [])
                if attempts:
                    last = attempts[-1].get("attempt", {})
                    failures = last.get("failureSummary", {}).get("failures", [])
                    if failures:
                        messages = [
                            f.get("failureOrigin", "") + ": " +
                            f.get("externalMessage", f.get("internalMessage", ""))
                            for f in failures
                        ]
                        failure_detail = "; ".join(m for m in messages if m.strip(" :"))
            except Exception:
                pass
            error_msg = f"Airbyte sync failed: {job_status}"
            if failure_detail:
                error_msg += f" — {failure_detail}"
            await update_sync_status(datasource_id, "error", error_msg)
            return

        # Sync succeeded — destination-embedding already sent all batches
        # and /ingest/batch marked completion on is_last_batch=True.
        logger.info("Airbyte sync job %d succeeded for %s", new_job_id, datasource_id)

        # Update mapping watermark
        try:
            await mapping_repo.update(datasource_id, last_processed_job_id=new_job_id)
        except Exception:
            pass

        # Optionally trigger Graph RAG
        if update_graph_rag:
            await _trigger_graph_rag_rebuild(datasource_id)

    except Exception as e:
        logger.exception(f"Unhandled error in ingestion for {datasource_id}")
        await update_sync_status(datasource_id, "error", str(e))


async def update_sync_status(uuid_str: str, status: str, error_msg: str | None):
    """Update final sync status with timestamp."""
    now = datetime.now(UTC).isoformat()

    ds_repo = DatasourceRepository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["sync_status"] = status
    meta["sync_progress"] = 100 if status == "completed" else 0
    meta["last_synced_at"] = now

    if error_msg:
        meta["last_error"] = error_msg
    else:
        meta.pop("last_error", None)

    await ds_repo.update_collection_metadata(uuid_str, meta)


async def update_sync_progress(uuid_str: str, stage: str, progress: int):
    """Update sync progress for real-time tracking."""
    ds_repo = DatasourceRepository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["sync_status"] = stage
    meta["sync_progress"] = progress

    await ds_repo.update_collection_metadata(uuid_str, meta)


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
    ds_repo = DatasourceRepository()
    row = await ds_repo.get_collection(uuid_str)
    if not row:
        return

    meta = row.get("cmetadata", {})
    meta["graph_update_status"] = graph_status
    if error:
        meta["graph_update_error"] = error
    else:
        meta.pop("graph_update_error", None)

    await ds_repo.update_collection_metadata(uuid_str, meta)
