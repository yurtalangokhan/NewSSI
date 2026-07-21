"""
Sync Queue Manager – deadlock-free sequential execution.

Design
------
* A single ``asyncio.Queue`` holds pending sync requests.
* A background worker coroutine drains the queue **one at a time**.
* Per-datasource ``asyncio.Lock``s prevent the *same* datasource from
  being enqueued twice (duplicate guard).
* Different datasources run sequentially so that the shared DB pool and
  embedding service are never overloaded.

This class is a **singleton** — acquire the instance via ``get_sync_queue()``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from core.logger import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------
# Data transfer object that travels through the queue
# ------------------------------------------------------------------


@dataclass
class SyncJob:
    """Represents a single sync request waiting in the queue."""

    datasource_id: str
    triggered_by: str = "scheduler"  # "scheduler" | "manual" | "api"
    update_graph_rag: bool = False
    # Filled in by the queue manager so callers can ``await`` completion.
    _done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    result_status: str | None = None
    result_error: str | None = None


# ------------------------------------------------------------------
# Queue manager
# ------------------------------------------------------------------


class SyncQueueManager:
    """FIFO queue that executes sync jobs one at a time."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self._max_queue_size = max_queue_size
        self._queue: asyncio.Queue[SyncJob] = asyncio.Queue(maxsize=max_queue_size)
        self._ds_locks: dict[str, asyncio.Lock] = {}
        self._active_job: SyncJob | None = None
        self._worker_task: asyncio.Task | None = None
        self._running = False
        # Public snapshot so the status endpoint can report queue position
        self._pending_ids: list[str] = []

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Start the background worker coroutine."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="sync-queue-worker")
        logger.info("SyncQueueManager worker started")

    async def stop(self) -> None:
        """Gracefully stop the worker (waits for current job to finish)."""
        self._running = False
        if self._worker_task:
            # Push a sentinel so the worker wakes up
            try:
                self._queue.put_nowait(None)  # type: ignore[arg-type]
            except asyncio.QueueFull:
                pass
            try:
                await self._worker_task
            except RuntimeError as exc:
                if "different event loop" not in str(exc):
                    raise
                self._worker_task.cancel()
            self._worker_task = None
        self._reset_runtime_state()
        logger.info("SyncQueueManager worker stopped")

    def _reset_runtime_state(self) -> None:
        self._queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._ds_locks = {}
        self._active_job = None
        self._pending_ids = []

    # ---- public API ------------------------------------------------------

    async def enqueue(self, job: SyncJob) -> bool:
        """Add a sync job to the queue.

        Returns *False* if the datasource already has a pending or active job.
        """
        ds_id = job.datasource_id

        # Per-datasource lock prevents double-enqueue
        lock = self._ds_locks.setdefault(ds_id, asyncio.Lock())
        if lock.locked():
            logger.warning("Datasource %s already has a sync in progress or queued", ds_id)
            return False

        try:
            self._queue.put_nowait(job)
            self._pending_ids.append(ds_id)
            logger.info("Enqueued sync for %s (queue depth=%d)", ds_id, self._queue.qsize())
            return True
        except asyncio.QueueFull:
            logger.error("Sync queue is full – rejecting job for %s", ds_id)
            return False

    def get_queue_position(self, datasource_id: str) -> int | None:
        """Return 0-based position in the pending list, or None if not queued."""
        try:
            return self._pending_ids.index(datasource_id)
        except ValueError:
            return None

    def is_active(self, datasource_id: str) -> bool:
        """Is this datasource's sync currently running?"""
        return self._active_job is not None and self._active_job.datasource_id == datasource_id

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    # ---- worker ----------------------------------------------------------

    async def _worker(self) -> None:
        """Long-running coroutine that processes jobs sequentially."""
        while self._running:
            try:
                job: SyncJob | None = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue

            if job is None:
                # Sentinel – shutdown requested
                break

            ds_id = job.datasource_id
            lock = self._ds_locks.setdefault(ds_id, asyncio.Lock())

            async with lock:
                self._active_job = job
                # Remove from pending list
                if ds_id in self._pending_ids:
                    self._pending_ids.remove(ds_id)

                try:
                    logger.info("Starting queued sync for %s", ds_id)
                    await self._execute_sync(job)
                except Exception:
                    logger.exception("Unhandled error executing sync for %s", ds_id)
                    job.result_status = "error"
                    job.result_error = "Internal queue worker error"
                finally:
                    self._active_job = None
                    job._done_event.set()
                    self._queue.task_done()

        logger.info("Sync queue worker exiting")

    async def _execute_sync(self, job: SyncJob) -> None:
        """Run the ingestion pipeline for a single job."""
        from service.IngestionService import run_ingestion

        try:
            await run_ingestion(job.datasource_id, update_graph_rag=job.update_graph_rag)
            job.result_status = "completed"
        except Exception as exc:
            logger.exception("Sync failed for %s", job.datasource_id)
            job.result_status = "error"
            job.result_error = str(exc)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_INSTANCE: SyncQueueManager | None = None


def get_sync_queue() -> SyncQueueManager:
    """Return the global SyncQueueManager (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SyncQueueManager()
    return _INSTANCE
