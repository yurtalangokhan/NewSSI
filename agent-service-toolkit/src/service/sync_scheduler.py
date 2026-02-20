"""
Sync Scheduler Service.

Wraps APScheduler's ``AsyncIOScheduler`` to fire cron-triggered sync jobs.

Responsibilities
----------------
* Start / stop with the FastAPI lifespan.
* On startup, load all enabled schedules from ``sync_schedules`` and register
  APScheduler ``CronTrigger`` jobs.
* Expose helpers so the schedule CRUD routes can add / remove / update jobs
  at runtime without restarting.
* Delegate actual sync execution to ``SyncQueueManager`` so that concurrent
  triggers are safely serialised.
"""

from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from service.schedule_db import ScheduleDBManager
from service.sync_queue import SyncJob, get_sync_queue

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Scheduler wrapper
# ------------------------------------------------------------------


class SyncScheduler:
    """Singleton wrapper around APScheduler for datasource sync jobs."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        )
        self._started = False

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Create the sync_schedules table, load persisted schedules, start APScheduler."""
        await ScheduleDBManager.ensure_table()

        schedules = await ScheduleDBManager.list_enabled()
        for sched in schedules:
            self._add_job_from_row(sched)

        self._scheduler.start()
        self._started = True
        logger.info(
            "SyncScheduler started with %d persisted schedule(s)", len(schedules)
        )

    async def stop(self) -> None:
        """Shutdown APScheduler gracefully."""
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("SyncScheduler stopped")

    # ---- runtime job management ------------------------------------------

    def add_job(self, schedule_row: dict) -> None:
        """Register (or replace) an APScheduler job from a DB row."""
        self._add_job_from_row(schedule_row)

    def remove_job(self, datasource_id: str) -> None:
        """Remove the APScheduler job for a datasource (idempotent)."""
        job_id = self._job_id(datasource_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Removed scheduler job %s", job_id)

    def update_job(self, schedule_row: dict) -> None:
        """Re-create the APScheduler job after a schedule update."""
        self.remove_job(schedule_row["datasource_id"])
        if schedule_row.get("enabled"):
            self._add_job_from_row(schedule_row)

    # ---- internal --------------------------------------------------------

    @staticmethod
    def _job_id(datasource_id: str) -> str:
        return f"sync-{datasource_id}"

    def _add_job_from_row(self, row: dict) -> None:
        """Parse the cron expression from *row* and add an APScheduler job."""
        ds_id = row["datasource_id"]
        cron_expr = row["cron_expression"]
        tz_name = row.get("timezone", "UTC")
        update_graph = row.get("update_graph_rag", False)

        parts = cron_expr.split()
        if len(parts) != 5:
            logger.error("Bad cron expression for %s: %r", ds_id, cron_expr)
            return

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=tz_name,
        )

        job_id = self._job_id(ds_id)
        # Replace if already exists
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        self._scheduler.add_job(
            _on_cron_trigger,
            trigger=trigger,
            id=job_id,
            args=[ds_id, update_graph],
            replace_existing=True,
        )
        logger.info("Scheduled sync for %s → cron=%s tz=%s", ds_id, cron_expr, tz_name)


# ------------------------------------------------------------------
# Callback invoked by APScheduler
# ------------------------------------------------------------------


async def _on_cron_trigger(datasource_id: str, update_graph_rag: bool) -> None:
    """Called by APScheduler on each cron tick.

    Enqueues a ``SyncJob`` into the ``SyncQueueManager`` so that
    multiple concurrent triggers are executed sequentially.
    After the job completes, update the schedule's last_run metadata.
    """
    logger.info("Cron trigger fired for datasource %s", datasource_id)

    queue = get_sync_queue()
    job = SyncJob(
        datasource_id=datasource_id,
        triggered_by="scheduler",
        update_graph_rag=update_graph_rag,
    )

    enqueued = await queue.enqueue(job)
    if not enqueued:
        logger.warning(
            "Skipping scheduled sync for %s – already running or queued", datasource_id
        )
        return

    # Wait for completion so we can record the outcome
    await job._done_event.wait()

    status = job.result_status or "unknown"
    error = job.result_error

    try:
        await ScheduleDBManager.mark_run_complete(datasource_id, status, error)
    except Exception:
        logger.exception("Failed to record run result for %s", datasource_id)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_INSTANCE: Optional[SyncScheduler] = None


def get_sync_scheduler() -> SyncScheduler:
    """Return the global SyncScheduler instance (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SyncScheduler()
    return _INSTANCE
