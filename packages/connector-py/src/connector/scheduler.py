"""Durable sync scheduler: cron expressions and fixed intervals.

Design
------
Scheduling state lives in a :class:`~connector.stores.ScheduleStore`, not in
memory. One polling loop asks the store "what is due?" and starts those runs:

* **Restart-safe.** ``next_run_at`` is persisted, so a run that came due while
  the service was down fires once on startup (``misfire="run_once"``) or is
  skipped to the next slot (``misfire="skip"``). Nothing is recomputed from
  "now" just because the process restarted.
* **Replica-safe.** Before starting a run the scheduler *claims* the slot with a
  compare-and-set on ``next_run_at``. With several replicas polling the same
  store exactly one wins; the others see the slot moved and do nothing.
* **Resumes interrupted work.** On ``start()`` jobs left RUNNING by a dead
  process are failed and, optionally, their connections are run again. Because
  incremental checkpoints are saved while a job progresses, the new run
  continues from the last checkpoint. With ``replicated=True`` (several
  replicas share the stores) only jobs whose heartbeat went stale count as
  dead, and the same check repeats on every poll, so a job whose worker died
  later, or whose heartbeat was still fresh at startup, is picked up too.

Cron expressions need the optional ``croniter`` dependency
(``pip install connector-py[scheduler]``); intervals need nothing.

``tick()`` is public so an external trigger (a Kubernetes CronJob, a test) can
drive the scheduler without the background loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal
from zoneinfo import ZoneInfo

from .errors import SyncAlreadyRunningError
from .extras import require_extra
from .models import Connection, Job, JobTrigger, Schedule, ScheduleEntry, utcnow
from .stores import ConnectionReader, InMemoryScheduleStore, ScheduleStore
from .sync import SyncRunner

logger = logging.getLogger("connector.scheduler")

Misfire = Literal["run_once", "skip"]


def next_run_at(schedule: Schedule, after: datetime | None = None) -> datetime:
    """Next fire time of ``schedule`` strictly after ``after`` (UTC)."""
    base = after or utcnow()
    if schedule.interval_seconds:
        return (base + timedelta(seconds=schedule.interval_seconds)).astimezone(UTC)
    croniter = require_extra("croniter", extra="scheduler", feature="a cron schedule").croniter
    tz = _zone(schedule.timezone)
    nxt: datetime = croniter(schedule.cron_expression, base.astimezone(tz)).get_next(datetime)
    return nxt.astimezone(UTC)


def _zone(name: str) -> tzinfo:
    """Resolve an IANA name; ``UTC`` needs no tz database (Windows lacks one without ``tzdata``)."""
    if name.upper() in {"UTC", "Z", "ETC/UTC"}:
        return UTC
    return ZoneInfo(name)


class SyncScheduler:
    def __init__(
        self,
        runner: SyncRunner,
        connections: ConnectionReader,
        schedules: ScheduleStore | None = None,
        *,
        poll_interval_seconds: float = 15.0,
        misfire: Misfire = "run_once",
        resume_interrupted: bool = True,
        replicated: bool = False,
        stale_after_seconds: float | None = None,
    ) -> None:
        """``replicated``: other processes run syncs against the same stores. A job is
        then only taken for dead once its heartbeat is older than the runner's
        ``stale_after_seconds`` (or the value given here, which also implies it)."""
        self.runner = runner
        self.connections = connections
        self.schedules: ScheduleStore = schedules or InMemoryScheduleStore()
        self.poll_interval_seconds = poll_interval_seconds
        self.misfire: Misfire = misfire
        self.resume_interrupted = resume_interrupted
        if stale_after_seconds is None and replicated:
            stale_after_seconds = runner.options.stale_after_seconds
        self.stale_after_seconds = stale_after_seconds
        self._task: asyncio.Task[None] | None = None

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> list[Job]:
        """Reconcile schedules, recover interrupted jobs, start polling.

        Returns the jobs that were started to resume interrupted work.
        """
        await self.sync_schedules()
        resumed = await self._recover()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="connector-scheduler")
        return resumed

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ---- schedule management ------------------------------------------------

    async def schedule(
        self, connection: Connection, *, now: datetime | None = None
    ) -> ScheduleEntry | None:
        """Create or refresh the entry of ``connection``. Call after every create/update.

        ``next_run_at`` is kept when the timing definition did not change, so
        editing an unrelated field never postpones or duplicates a run.
        """
        sched = connection.schedule
        if sched is None or not sched.enabled:
            await self.schedules.delete(connection.id)
            return None
        now = now or utcnow()
        existing = await self.schedules.get(connection.id)
        fingerprint = sched.fingerprint()
        if existing is not None and existing.fingerprint == fingerprint and existing.next_run_at:
            return existing
        first = now if sched.run_on_create and existing is None else next_run_at(sched, now)
        entry = ScheduleEntry(
            connection_id=connection.id,
            next_run_at=first,
            last_run_at=existing.last_run_at if existing else None,
            last_job_id=existing.last_job_id if existing else None,
            fingerprint=fingerprint,
        )
        return await self.schedules.upsert(entry)

    async def unschedule(self, connection_id: str) -> None:
        await self.schedules.delete(connection_id)

    async def sync_schedules(self) -> int:
        """Make the schedule store match the connection store. Returns active entries."""
        connections = {c.id: c for c in await self.connections.list()}
        for entry in await self.schedules.list():
            conn = connections.get(entry.connection_id)
            if conn is None or conn.schedule is None or not conn.schedule.enabled:
                await self.schedules.delete(entry.connection_id)
        active = 0
        for conn in connections.values():
            try:
                if await self.schedule(conn) is not None:
                    active += 1
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - e.g. an unparseable cron; keep the others
                logger.exception("connection %s could not be scheduled", conn.id)
        return active

    async def next_runs(self) -> dict[str, datetime | None]:
        return {e.connection_id: e.next_run_at for e in await self.schedules.list()}

    # ---- execution ------------------------------------------------------------------

    async def tick(self, now: datetime | None = None) -> list[Job]:
        """Start every run that is due. Safe to call from several processes at once."""
        now = now or utcnow()
        started: list[Job] = []
        for entry in await self.schedules.list_due(now):
            try:
                job = await self._run_due(entry, now)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one broken connection must not starve the rest
                logger.exception(
                    "scheduled run of connection %s could not be started", entry.connection_id
                )
                continue
            if job is not None:
                started.append(job)
        return started

    async def _run_due(self, entry: ScheduleEntry, now: datetime) -> Job | None:
        conn = await self.connections.get(entry.connection_id)
        if conn is None or conn.schedule is None or not conn.schedule.enabled:
            await self.schedules.delete(entry.connection_id)
            return None
        upcoming = self._upcoming(entry, conn.schedule, now)
        if not await self.schedules.claim(entry.connection_id, entry.next_run_at, upcoming):
            return None  # another replica took this slot
        if self._is_misfire(entry, conn.schedule, now) and self.misfire == "skip":
            logger.info("connection %s missed its slot; skipping to %s", conn.id, upcoming)
            return None
        try:
            job = await self._start(conn, JobTrigger.SCHEDULE)
        except (Exception, asyncio.CancelledError):
            # The slot was taken and nothing ran. Left like that the run would be lost
            # until the next slot, which for a daily schedule is a day away.
            await self._give_back(entry, upcoming)
            raise
        if job is not None:
            await self._record_run(conn.id, job, now)
        return job

    async def _give_back(self, entry: ScheduleEntry, claimed: datetime) -> None:
        """Undo the claim of ``entry``'s slot, so the next poll finds it due again."""
        if entry.next_run_at is None:
            return
        try:
            await self.schedules.claim(entry.connection_id, claimed, entry.next_run_at)
        except Exception:  # noqa: BLE001 - best effort; the failure to start is what matters
            logger.exception("slot of connection %s could not be given back", entry.connection_id)

    @staticmethod
    def _upcoming(entry: ScheduleEntry, schedule: Schedule, now: datetime) -> datetime:
        """Next slot. Intervals advance from the previous slot so they do not drift with
        polling delay; after a long outage they restart from ``now``."""
        if schedule.interval_seconds and entry.next_run_at is not None:
            candidate = next_run_at(schedule, entry.next_run_at)
            if candidate > now:
                return candidate
        return next_run_at(schedule, now)

    def _is_misfire(self, entry: ScheduleEntry, schedule: Schedule, now: datetime) -> bool:
        if entry.next_run_at is None:
            return False
        grace = max(self.poll_interval_seconds * 2, 60.0)
        return (now - entry.next_run_at).total_seconds() > grace

    async def _start(self, connection: Connection, trigger: JobTrigger) -> Job | None:
        try:
            return await self.runner.start(connection, trigger=trigger)
        except SyncAlreadyRunningError as exc:  # here or on a sibling: not an error
            logger.info("connection %s not started: %s", connection.id, exc)
            return None

    async def _record_run(self, connection_id: str, job: Job, now: datetime) -> None:
        entry = await self.schedules.get(connection_id)
        if entry is None:
            return
        entry.last_run_at = now
        entry.last_job_id = job.id
        entry.updated_at = now
        await self.schedules.upsert(entry)

    async def _recover(self) -> list[Job]:
        interrupted = await self.runner.recover_interrupted(self.stale_after_seconds)
        if not interrupted:
            return []
        logger.warning("%d job(s) were interrupted by a shutdown", len(interrupted))
        if not self.resume_interrupted:
            return []
        resumed: list[Job] = []
        for connection_id in dict.fromkeys(j.connection_id for j in interrupted):
            try:
                conn = await self.connections.get(connection_id)
                job = await self._start(conn, JobTrigger.RESUME) if conn is not None else None
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the other interrupted connections still resume
                logger.exception("interrupted connection %s could not be resumed", connection_id)
                continue
            if job is not None:
                resumed.append(job)
        return resumed

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
                if self.stale_after_seconds is not None:
                    # With several replicas a sibling can die after this one started;
                    # its jobs only look dead once their heartbeat goes stale.
                    await self._recover()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the scheduler alive
                logger.exception("scheduler tick failed")
            await asyncio.sleep(self.poll_interval_seconds)
