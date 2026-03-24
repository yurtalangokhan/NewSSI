"""
Airbyte Sync Listener — post-sync bookkeeping.

A background ``asyncio.Task`` that polls the Airbyte API for completed
sync jobs and updates the watermark (``last_processed_job_id``).

With the streaming architecture, embedding happens **during** sync via
the custom ``destination-embedding`` connector → ``/ingest/batch``.
The listener only needs to:
1. Detect newly completed jobs.
2. Update the watermark so the same job isn't processed twice.
3. Optionally trigger a Graph RAG rebuild.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("AIRBYTE_SYNC_POLL_INTERVAL_SECONDS", "30"))


class AirbyteSyncListener:
    """Polls Airbyte for completed sync jobs and updates watermarks."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Start the background polling task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="airbyte-sync-listener")
        logger.info("AirbyteSyncListener started (poll every %ds)", POLL_INTERVAL)

    async def stop(self) -> None:
        """Gracefully stop the listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("AirbyteSyncListener stopped")

    # ---- main loop -------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Long-running coroutine that checks for completed Airbyte jobs."""
        # Initial delay to let services warm up
        await asyncio.sleep(10)

        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in sync listener poll cycle")

            try:
                await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _poll_once(self) -> None:
        """Single poll cycle: check all mapped datasources for new completed jobs."""
        from service.airbyte_mapping_db import AirbyteMappingDB
        from service.airbyte_api_client import get_airbyte_client

        mappings = await AirbyteMappingDB.list_all()
        if not mappings:
            return

        client = get_airbyte_client()

        for mapping in mappings:
            ds_id = mapping["datasource_id"]
            conn_id = mapping["airbyte_connection_id"]
            last_processed = mapping.get("last_processed_job_id", 0) or 0
            update_graph = mapping.get("update_graph_rag", False)

            try:
                jobs = await client.list_jobs(conn_id, limit=5)

                # Find new completed jobs (id > last_processed)
                new_completed = []
                for job_entry in jobs:
                    job = job_entry.get("job", job_entry)
                    job_id = job.get("id", 0)
                    status = job.get("status", "")

                    if job_id > last_processed and status == "succeeded":
                        new_completed.append(job)

                if not new_completed:
                    continue

                # Sort by ID ascending — process oldest first
                new_completed.sort(key=lambda j: j.get("id", 0))

                for job in new_completed:
                    job_id = job.get("id", 0)
                    logger.info(
                        "Processing completed Airbyte job %d for datasource %s",
                        job_id,
                        ds_id,
                    )

                    try:
                        await self._process_completed_job(
                            ds_id, conn_id, job_id, update_graph
                        )

                        # Update last_processed_job_id on success
                        await AirbyteMappingDB.update(
                            ds_id, last_processed_job_id=job_id
                        )
                        logger.info(
                            "Ingestion complete for job %d / datasource %s",
                            job_id,
                            ds_id,
                        )

                    except Exception:
                        logger.exception(
                            "Ingestion failed for job %d / datasource %s — will retry next cycle",
                            job_id,
                            ds_id,
                        )
                        # Do NOT update last_processed_job_id so retry happens
                        break  # Stop processing this datasource's jobs

            except Exception:
                logger.exception(
                    "Failed to check jobs for datasource %s (connection %s)",
                    ds_id,
                    conn_id,
                )

    async def _process_completed_job(
        self,
        datasource_id: str,
        connection_id: str,
        job_id: int,
        update_graph_rag: bool,
    ) -> None:
        """Update sync status and optionally trigger Graph RAG rebuild.

        With the streaming architecture, data has **already** been embedded
        during the sync by ``destination-embedding`` → ``/ingest/batch``.
        There is no post-sync extraction/embedding step.
        """
        from service.ingestion import update_sync_status, _trigger_graph_rag_rebuild

        await update_sync_status(datasource_id, "completed", None)

        if update_graph_rag:
            try:
                await _trigger_graph_rag_rebuild(datasource_id)
            except Exception:
                logger.exception(
                    "Graph RAG rebuild failed for datasource %s", datasource_id
                )


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_INSTANCE: Optional[AirbyteSyncListener] = None


def get_sync_listener() -> AirbyteSyncListener:
    """Return the global AirbyteSyncListener (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AirbyteSyncListener()
    return _INSTANCE
