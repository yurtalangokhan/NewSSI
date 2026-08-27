"""
Sync Scheduler Service.

Wraps APScheduler's ``AsyncIOScheduler`` to fire cron-triggered sync jobs.

Responsibilities
----------------
* Start / stop with the FastAPI lifespan.
* On startup, load all enabled schedules from ``sync_schedules`` and register
  APScheduler ``CronTrigger`` jobs.
* Detect missed runs (where ``next_run_at`` has passed during downtime) and
  fire them immediately so no scheduled sync is silently lost.
* Refresh ``next_run_at`` in the database after restart so the UI stays
  accurate.
* Expose helpers so the schedule CRUD routes can add / remove / update jobs
  at runtime without restarting.
* Delegate actual sync execution to ``SyncQueueManager`` so that concurrent
  triggers are safely serialised.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.logger import get_logger
from repository.schedule_repository import ScheduleDBManager
from service.SyncQueueService import SyncJob, get_sync_queue

logger = get_logger(__name__)

# Maximum number of attempts to load schedules from the DB on startup.
_STARTUP_DB_RETRIES = 5
_STARTUP_DB_DELAY = 2  # seconds between retries


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
        """Create the sync_schedules table, load persisted schedules, start APScheduler.

        Improvements over the naïve approach:
        * Retries the DB read if the pool isn't ready yet.
        * Isolates errors per-schedule so one bad row can't block the rest.
        * Refreshes ``next_run_at`` in the DB after computing the real next
          fire time from the cron expression.
        * Fires any schedules whose ``next_run_at`` fell into the past while
          the service was down (catch-up).
        """
        await ScheduleDBManager.ensure_table()

        # -- load with retry (DB pool may not be warm yet) -----------------
        schedules: list[dict] = []
        for attempt in range(1, _STARTUP_DB_RETRIES + 1):
            try:
                schedules = await ScheduleDBManager.list_enabled()
                break
            except Exception:
                if attempt == _STARTUP_DB_RETRIES:
                    logger.exception(
                        "Failed to load sync schedules after %d attempts – scheduler starts empty",
                        _STARTUP_DB_RETRIES,
                    )
                else:
                    logger.warning(
                        "DB not ready for schedule load (attempt %d/%d), retrying in %ds …",
                        attempt,
                        _STARTUP_DB_RETRIES,
                        _STARTUP_DB_DELAY,
                    )
                    await asyncio.sleep(_STARTUP_DB_DELAY)

        # -- register each schedule (error-isolated) -----------------------
        loaded = 0
        missed_ds_ids: list[tuple[str, bool]] = []  # (datasource_id, update_graph_rag)
        now = datetime.now(UTC)

        for sched in schedules:
            try:
                self._add_job_from_row(sched)
                loaded += 1

                # Detect missed runs: next_run_at is in the past
                raw_next = sched.get("next_run_at")
                if raw_next is not None:
                    if isinstance(raw_next, str):
                        next_dt = datetime.fromisoformat(raw_next)
                    else:
                        next_dt = raw_next
                    if next_dt.tzinfo is None:
                        next_dt = next_dt.replace(tzinfo=UTC)
                    if next_dt < now:
                        missed_ds_ids.append(
                            (sched["datasource_id"], sched.get("update_graph_rag", False))
                        )

                # Refresh next_run_at in DB to the real next fire time
                await self._refresh_next_run(sched)

            except Exception:
                logger.exception(
                    "Failed to restore schedule for datasource %s – skipping",
                    sched.get("datasource_id", "?"),
                )

        self._scheduler.start()
        self._started = True
        logger.info(
            "SyncScheduler started: %d/%d schedule(s) restored, %d missed run(s) detected",
            loaded,
            len(schedules),
            len(missed_ds_ids),
        )

        # -- fire missed runs in the background ----------------------------
        if missed_ds_ids:
            asyncio.create_task(
                self._catchup_missed(missed_ds_ids),
                name="sync-scheduler-catchup",
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

    async def _refresh_next_run(self, sched: dict) -> None:
        """Recompute ``next_run_at`` from the cron expression and persist it."""
        try:
            ds_id = sched["datasource_id"]
            cron_expr = sched["cron_expression"]
            tz_name = sched.get("timezone", "UTC")
            next_run = ScheduleDBManager.compute_next_run(cron_expr, tz_name)
            await ScheduleDBManager.update(ds_id, next_run_at=next_run)
            logger.debug("Refreshed next_run_at for %s → %s", ds_id, next_run.isoformat())
        except Exception:
            logger.exception(
                "Failed to refresh next_run_at for %s",
                sched.get("datasource_id", "?"),
            )

    async def _catchup_missed(self, missed: list[tuple[str, bool]]) -> None:
        """Fire catch-up syncs for schedules whose ``next_run_at`` was in the past.

        Runs as a background task after the scheduler has fully started so
        it doesn't block the FastAPI lifespan.
        """
        # Small delay to let the rest of the app finish starting up
        await asyncio.sleep(3)

        queue = get_sync_queue()
        for ds_id, update_graph in missed:
            logger.info(
                "Catch-up: firing missed sync for datasource %s (update_graph_rag=%s)",
                ds_id,
                update_graph,
            )
            job = SyncJob(
                datasource_id=ds_id,
                triggered_by="scheduler-catchup",
                update_graph_rag=update_graph,
            )
            enqueued = await queue.enqueue(job)
            if not enqueued:
                logger.warning("Catch-up: skipped %s – already running or queued", ds_id)
                continue

            # Wait for completion so we can record the outcome
            await job._done_event.wait()
            status = job.result_status or "unknown"
            error = job.result_error
            try:
                await ScheduleDBManager.mark_run_complete(ds_id, status, error)
            except Exception:
                logger.exception("Catch-up: failed to record run result for %s", ds_id)


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
        logger.warning("Skipping scheduled sync for %s – already running or queued", datasource_id)
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

_INSTANCE: SyncScheduler | None = None


def get_sync_scheduler() -> SyncScheduler:
    """Return the global SyncScheduler instance (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = SyncScheduler()
    return _INSTANCE
