"""Sync runner: moves records from a source to a destination in bounded batches.

Responsibilities (and only these):

* obtain the source / destination of a connection from a :class:`ConnectorFactory`
* stream ``source.read()`` and buffer per stream up to ``batch_size``
* flush to ``destination.write()`` with retry, honouring ``State`` checkpoints
* record progress in a :class:`Job` and persist it through the stores

Memory is bounded by ``batch_size × streams``: a batch is released as soon as
the destination acknowledges it.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .base import BaseConnector, BaseDestination, BaseSource
from .errors import (
    CheckFailedError,
    DestinationWriteError,
    JobNotFoundError,
    JobTakenOverError,
    SyncAlreadyRunningError,
)
from .factory import ConnectorFactory, RegistryConnectorFactory
from .models import (
    Batch,
    Connection,
    Job,
    JobStatus,
    JobTrigger,
    Record,
    State,
    StreamStats,
    SyncMode,
    SyncState,
    WriteResult,
    utcnow,
)
from .redaction import redact_secrets
from .registry import ConnectorRegistry
from .stores import ExclusiveJobStore, InMemoryJobStore, InMemoryStateStore, JobStore, StateStore

logger = logging.getLogger("connector.sync")

JobHook = Callable[[Job], Awaitable[None]]
ProgressHook = JobHook
_ConnectorT = TypeVar("_ConnectorT", bound=BaseConnector[Any])

STALE_JOB_REASON = "interrupted: its worker stopped responding"
SUPERSEDED_JOB_REASON = "superseded: another worker declared this job dead and took over"


@dataclass
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def delay(self, attempt: int) -> float:
        return min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)


@dataclass
class SyncOptions:
    batch_size: int = 200
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    checkpoint_state: bool = True
    progress_hook: JobHook | None = None
    """Called after every persisted step of a job (each batch, each status change)."""
    status_hook: JobHook | None = None
    """Called once per status of a job: pending when it is created (before ``start()``
    returns), running, then its final status. A start that is refused creates no job
    and reports nothing.

    Both hooks are observers: an exception they raise is logged and the sync goes on."""
    connector_factory_allow_hidden: bool = False
    """Let the default registry factory build connectors the visibility policy hides."""
    timeout_seconds: float | None = None
    """Fail the job if it runs longer than this."""
    check_before_sync: bool = False
    """Run ``check()`` on source and destination before moving data."""
    allow_concurrent_jobs: bool = False
    """Permit two jobs of the same connection at once. Off by default."""
    heartbeat_interval_seconds: float = 30.0
    """How often a running job refreshes ``heartbeat_at`` in the job store."""
    stale_after_seconds: float = 300.0
    """A non-terminal job whose heartbeat is older than this belongs to a dead process."""
    max_concurrent_jobs: int | None = None
    """Jobs this runner executes at once. Further jobs stay
    PENDING, keep their heartbeat, and start in turn. ``None``: no limit."""


class SyncRunner:
    """Executes one :class:`Connection` as a :class:`Job`.

    ``connectors`` is either a registry (connectors are built from the
    configurations stored on the connection) or any :class:`ConnectorFactory`.
    """

    def __init__(
        self,
        connectors: ConnectorRegistry | ConnectorFactory,
        *,
        state_store: StateStore | None = None,
        job_store: JobStore | None = None,
        options: SyncOptions | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.options = options or SyncOptions()
        self.factory: ConnectorFactory = (
            RegistryConnectorFactory(
                connectors, allow_hidden=self.options.connector_factory_allow_hidden
            )
            if isinstance(connectors, ConnectorRegistry)
            else connectors
        )
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.state_store = state_store or InMemoryStateStore()
        self.job_store = job_store or InMemoryJobStore()
        self._running: dict[str, asyncio.Task[Job]] = {}
        self._active: dict[str, str] = {}  # connection_id -> job_id currently executing
        self._reported: dict[str, JobStatus] = {}  # job_id -> status the status hook last saw
        self._taken_over: set[str] = set()  # jobs whose heartbeat found them ended by a sibling
        limit = self.options.max_concurrent_jobs
        self._slots = asyncio.Semaphore(limit) if limit else None
        self._shutting_down = False

    # ---- public API -------------------------------------------------------

    async def run(
        self,
        connection: Connection,
        *,
        full_refresh: bool = False,
        trigger: JobTrigger = JobTrigger.MANUAL,
    ) -> Job:
        """Run synchronously and return the finished job."""
        job = await self._create_job(connection, trigger)
        return await self._execute(connection, job, full_refresh=full_refresh)

    async def start(
        self,
        connection: Connection,
        *,
        full_refresh: bool = False,
        trigger: JobTrigger = JobTrigger.MANUAL,
    ) -> Job:
        """Run in the background; returns the pending job immediately.

        Raises :class:`SyncAlreadyRunningError` when the connection already has
        a live job (unless ``allow_concurrent_jobs``).
        """
        job = await self._create_job(connection, trigger)
        task = asyncio.create_task(
            self._execute(connection, job, full_refresh=full_refresh),
            name=f"connector-sync-{job.id}",
        )
        self._running[job.id] = task

        def forget(_task: asyncio.Task[Job]) -> None:
            self._running.pop(job.id, None)
            # A task cancelled before its first step never ran the cleanup inside
            # ``_execute``: without this the connection would stay taken in this process.
            if self._active.get(connection.id) == job.id:
                self._active.pop(connection.id, None)
            self._reported.pop(job.id, None)

        task.add_done_callback(forget)
        return job

    async def cancel(self, job_id: str) -> bool:
        task = self._running.get(job_id)
        if task is None or task.done():
            return False
        # Cancelled before its first step, the coroutine never runs: nothing inside
        # it will mark the job cancelled, so that has to happen here.
        coro = task.get_coro()
        unstarted = (
            inspect.iscoroutine(coro) and inspect.getcoroutinestate(coro) == inspect.CORO_CREATED
        )
        task.cancel()
        if unstarted:
            job = await self.job_store.get(job_id)
            if job is not None and not job.is_terminal:
                await self._close_unstarted(job)
        return True

    async def shutdown(self) -> int:
        """Stop the background jobs of this process without finishing them.

        Unlike :meth:`cancel`, the jobs are left PENDING/RUNNING in the job store:
        the process is going away, the work is not. The next start sees them as
        interrupted (:meth:`recover_interrupted`) and the scheduler runs their
        connections again from the last checkpoint. Returns the number interrupted.
        """
        self._shutting_down = True
        tasks = [task for task in self._running.values() if not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    async def wait(self, job_id: str) -> Job:
        """The finished job. Cancelling the waiter leaves the job running."""
        task = self._running.get(job_id)
        if task is not None:
            # Not ``await task``: that would pass a cancellation of the waiter on to
            # the job, and take a cancellation of the job for one of the waiter.
            await asyncio.wait({task})
            if not task.cancelled():
                return task.result()
        job = await self.job_store.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def active_job_id(self, connection_id: str) -> str | None:
        """Id of the job currently executing for ``connection_id``, if any."""
        return self._active.get(connection_id)

    async def recover_interrupted(
        self,
        stale_after_seconds: float | None = None,
        reason: str = "interrupted by service restart",
    ) -> list[Job]:
        """Fail jobs that a dead process left PENDING/RUNNING and return them.

        ``stale_after_seconds=None`` treats every non-terminal job that this
        runner does not own as dead: right for a single-process deployment.
        With several replicas pass a threshold (a few heartbeat intervals) so
        that jobs of live siblings, whose heartbeat is fresh, are left alone.

        Incremental checkpoints are stored as the job progresses, so running the
        connection again continues from the last checkpoint instead of starting over.
        """
        recovered: list[Job] = []
        own = {*self._running, *self._active.values()}  # started here, or inside run()
        for job in await self.job_store.list_active():
            if job.id in own:
                continue
            if stale_after_seconds is not None and self._is_alive(job, stale_after_seconds):
                continue
            await self._fail(job, reason)
            recovered.append(job)
        return recovered

    async def has_active_job(self, connection_id: str) -> bool:
        """True if this process or a live sibling is running the connection."""
        if connection_id in self._active:
            return True
        return any(
            self._is_alive(job, self.options.stale_after_seconds)
            for job in await self.job_store.list_active(connection_id)
        )

    # ---- job creation -----------------------------------------------------

    @staticmethod
    def _is_alive(job: Job, stale_after_seconds: float) -> bool:
        beat = job.heartbeat_at or job.created_at
        return (utcnow() - beat).total_seconds() < stale_after_seconds

    async def _fail(self, job: Job, reason: str) -> None:
        """Close a job whose worker is gone. Its heartbeat stays as the worker left it."""
        job.status = JobStatus.FAILED
        job.error = reason
        job.finished_at = utcnow()
        await self.job_store.update(job)
        # The worker that would have reported this final status never will.
        try:
            await self._report_status(job)
            await self._call_hook(self.options.progress_hook, job)
        finally:
            self._reported.pop(job.id, None)

    async def _create_job(
        self, connection: Connection, trigger: JobTrigger = JobTrigger.MANUAL
    ) -> Job:
        job = Job(
            connection_id=connection.id,
            trigger=trigger,
            worker_id=self.worker_id,
            heartbeat_at=utcnow(),
        )
        if self.options.allow_concurrent_jobs:
            await self.job_store.create(job)
            self._active[connection.id] = job.id
        else:
            current = self._active.get(connection.id)
            if current is not None:
                raise SyncAlreadyRunningError(connection.id, current)
            # Reserved before the first await: a second start() in this process sees it.
            self._active[connection.id] = job.id
            try:
                await self._claim_connection(job)
            except BaseException:
                if self._active.get(connection.id) == job.id:
                    self._active.pop(connection.id, None)
                raise
        try:
            # Reported before the job can take a step, so "pending" never arrives late.
            await self._report_status(job)
        except BaseException:
            # The caller was cancelled while the observer ran (the hook's own errors
            # are swallowed): the job is stored and nobody is going to run it.
            await self._close_unstarted(job)
            raise
        return job

    async def _close_unstarted(self, job: Job) -> None:
        """End a stored job that will never execute, and free its connection."""
        if self._active.get(job.connection_id) == job.id:
            self._active.pop(job.connection_id, None)
        job.status = JobStatus.CANCELLED
        job.error = "cancelled before it started"
        job.finished_at = utcnow()
        try:
            await self._persist(job)
        except Exception:  # noqa: BLE001 - the stale-job takeover closes it otherwise
            logger.exception("could not close job %s, which never started", job.id)
        finally:
            self._reported.pop(job.id, None)

    async def _claim_connection(self, job: Job) -> None:
        """Store ``job`` as the only live job of its connection, or raise."""
        for other in await self.job_store.list_active(job.connection_id):
            if self._is_alive(other, self.options.stale_after_seconds):
                raise SyncAlreadyRunningError(job.connection_id, other.id, other.worker_id)
            # Left behind by a process that is gone. It must not block the connection.
            await self._fail(other, STALE_JOB_REASON)
        if isinstance(self.job_store, ExclusiveJobStore):
            # Atomic in the store: a sibling replica that passed the check above at
            # the same moment loses here.
            if await self.job_store.create_exclusive(job) is None:
                raise SyncAlreadyRunningError(job.connection_id)
        else:
            await self.job_store.create(job)

    # ---- execution --------------------------------------------------------

    async def _execute(self, connection: Connection, job: Job, *, full_refresh: bool) -> Job:
        run = asyncio.current_task()
        assert run is not None
        beat = asyncio.create_task(self._heartbeat(job, run), name=f"connector-heartbeat-{job.id}")
        holds_slot = False
        secrets: list[str] = []  # of the connectors of this run; kept out of job.error
        deadline: asyncio.Timeout | None = None

        try:
            if self._slots is not None:
                await self._slots.acquire()  # waits here as PENDING while the runner is full
                holds_slot = True
            job.status = JobStatus.RUNNING
            job.started_at = utcnow()
            await self._persist(job)
            # The limit covers everything the job does: building and opening the
            # connectors and the preflight check hang as readily as the sync itself.
            async with (
                asyncio.timeout(self.options.timeout_seconds) as deadline,
                contextlib.AsyncExitStack() as stack,
            ):
                source = await self._open(stack, await self.factory.source(connection), job)
                secrets += source.secret_values()
                destination = await self._open(
                    stack, await self.factory.destination(connection), job
                )
                secrets += destination.secret_values()
                if self.options.check_before_sync:
                    await self._preflight(source, destination)
                await self._sync(connection, job, source, destination, full_refresh)
            job.status = JobStatus.SUCCEEDED
        except asyncio.CancelledError:
            if job.id in self._taken_over:
                # The heartbeat learned that a sibling ended this job: the run stops
                # here, as a failure of this worker, and nothing is written as live.
                self._superseded(job)
            else:
                if not self._shutting_down:
                    job.status = JobStatus.CANCELLED
                    job.error = "cancelled"
                raise
        except JobTakenOverError:
            self._superseded(job)
        except Exception as exc:  # noqa: BLE001 - job boundary
            job.status = JobStatus.FAILED
            if deadline is not None and deadline.expired():
                # The job's own limit. A TimeoutError raised by a source is a failure of
                # the source like any other, and is reported as one below.
                logger.error(
                    "sync job %s timed out after %ss", job.id, self.options.timeout_seconds
                )
                job.error = f"timed out after {self.options.timeout_seconds}s"
            else:
                logger.exception("sync job %s failed", job.id)
                # The job is stored and shown to people who may not see the configuration.
                job.error = redact_secrets(f"{type(exc).__name__}: {exc}", secrets)
        finally:
            # Whatever happens from here on, the connection and the slot are given back:
            # a job that could not be closed must not keep later jobs from running.
            try:
                await self._stop(beat)
            finally:
                if self._active.get(connection.id) == job.id:
                    self._active.pop(connection.id, None)
                try:
                    if job.is_terminal:
                        job.finished_at = utcnow()
                        # The slot is kept through the final hooks, so post-sync work
                        # done there is covered by the concurrency limit as well.
                        await self._store_final(job)
                    # else: interrupted by shutdown(); the stored job stays non-terminal.
                finally:
                    self._reported.pop(job.id, None)
                    self._taken_over.discard(job.id)
                    if holds_slot and self._slots is not None:
                        self._slots.release()
        return job

    @staticmethod
    def _superseded(job: Job) -> None:
        logger.error("sync job %s was ended by another worker; stopping this run", job.id)
        job.status = JobStatus.FAILED
        job.error = SUPERSEDED_JOB_REASON

    @staticmethod
    async def _open(
        stack: contextlib.AsyncExitStack, connector: _ConnectorT, job: Job
    ) -> _ConnectorT:
        """Enter ``connector`` for the length of the run.

        Closing it is not part of the sync: a ``close()`` that fails is logged and
        changes neither a completed job nor the reason a failed one gives.
        """
        opened = await connector.__aenter__()

        async def close(*exc_info: Any) -> bool:
            try:
                await connector.__aexit__(*exc_info)
            except asyncio.CancelledError:
                # A connector's close may let a cancellation of its own out (aiokafka's
                # idle consumer); only a cancellation of this run is ours to propagate.
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                logger.exception("closing %s failed for job %s", connector.name(), job.id)
            except Exception:  # noqa: BLE001 - the run already has its outcome
                logger.exception("closing %s failed for job %s", connector.name(), job.id)
            return False

        stack.push_async_exit(close)
        return opened

    @staticmethod
    async def _stop(beat: asyncio.Task[None]) -> None:
        beat.cancel()
        try:
            await beat
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - a dead heartbeat must not undo the job's ending
            logger.exception("heartbeat task ended with an error")

    async def _store_final(self, job: Job) -> None:
        """:meth:`_persist_final`; for a background job a store that stays down is logged.

        ``run()`` has a caller to raise to. A ``start()`` task has none: an exception
        left on it would surface only as "Task exception was never retrieved", if ever.
        """
        try:
            await self._persist_final(job)
        except Exception:
            if job.id not in self._running:
                raise
            logger.exception(
                "final status of background job %s (%s) was not stored", job.id, job.status.value
            )

    async def _persist_final(self, job: Job) -> None:
        """Store the final status of ``job``; a store that fails is asked again.

        Left unwritten, the job would stay RUNNING in the store with nobody
        executing it, until its heartbeat went stale.
        """
        policy = self.options.retry
        attempts = max(policy.attempts, 1)
        for attempt in range(1, attempts + 1):
            try:
                await self._persist(job)
                return
            except Exception as exc:  # noqa: BLE001 - retried
                if attempt == attempts:
                    raise
                logger.warning(
                    "final status of job %s could not be stored (attempt %d/%d): %s",
                    job.id,
                    attempt,
                    attempts,
                    exc,
                )
                await asyncio.sleep(policy.delay(attempt))

    @staticmethod
    async def _preflight(source: BaseSource[Any], destination: BaseDestination[Any]) -> None:
        for label, connector in (("source", source), ("destination", destination)):
            result = await connector.check_connection()
            if not result.ok:
                raise CheckFailedError(f"{label} check failed: {result.message or 'unknown error'}")

    async def _sync(
        self,
        connection: Connection,
        job: Job,
        source: BaseSource[Any],
        destination: BaseDestination[Any],
        full_refresh: bool,
    ) -> None:
        catalog = connection.catalog
        incremental = any(s.sync_mode is SyncMode.INCREMENTAL for s in catalog.streams)
        if full_refresh:
            # "Start over" holds even when this run fails: the saved cursors go before
            # the first record is read, so no later run continues from them.
            await self.state_store.reset(connection.id)
        state = (
            SyncState()
            if (full_refresh or not incremental)
            else await self.state_store.load(connection.id)
        )

        buffers: dict[str, list[Record]] = {name: [] for name in catalog.names()}
        indices: dict[str, int] = dict.fromkeys(buffers, 0)
        for name in buffers:
            job.stats.setdefault(name, StreamStats())

        async def flush(stream: str, *, final: bool = False) -> None:
            records = buffers[stream]
            if not records and not (final and destination.needs_final_batch):
                return
            buffers[stream] = []  # release before the (possibly slow) write
            batch = Batch(
                stream=stream,
                records=records,
                batch_index=indices[stream],
                is_last=final,
                connection_id=connection.id,
                source_name=connection.source_name,
                job_id=job.id,
            )
            result = await self._write_with_retry(destination, batch)
            indices[stream] += 1
            stats = job.stats[stream]
            stats.batches += 1
            stats.records_written += result.records_written
            await self._persist(job)
            # Cooperative cancellation point: in-memory sources/destinations may
            # never yield to the event loop otherwise, making cancel() a no-op.
            await asyncio.sleep(0)

        await destination.begin(catalog, connection.id, job_id=job.id)
        try:
            items = source.read(catalog, state)
            try:
                async for item in items:
                    if isinstance(item, Record):
                        stream = item.stream
                        if stream not in buffers:
                            # Source emitted a stream that was not selected; ignore.
                            continue
                        buffers[stream].append(item)
                        job.stats[stream].records_read += 1
                        if len(buffers[stream]) >= self.options.batch_size:
                            await flush(stream)
                    elif isinstance(item, State):
                        if item.stream in buffers:
                            await flush(item.stream)
                        state.update(item)
                        if self.options.checkpoint_state and incremental:
                            await self.state_store.save(connection.id, state)
            finally:
                # Run the source's own cleanup (cursors, scrolls) now, not at GC time.
                aclose = getattr(items, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:  # noqa: BLE001 - not what the run ended with
                        # Raised here it would replace the failure, the cancellation or
                        # the timeout that is the real outcome of the run.
                        logger.exception("source cleanup failed for job %s", job.id)

            for stream in buffers:
                await flush(stream, final=True)
            await destination.finalize(catalog, connection.id, job_id=job.id)
        except (Exception, asyncio.CancelledError) as exc:
            try:
                await destination.abort(catalog, connection.id, job_id=job.id, error=exc)
            except Exception:  # noqa: BLE001 - the original failure is the one to report
                logger.exception("destination abort failed for job %s", job.id)
            raise

        if self.options.checkpoint_state and incremental:
            await self.state_store.save(connection.id, state)

    async def _write_with_retry(
        self, destination: BaseDestination[Any], batch: Batch
    ) -> WriteResult:
        policy = self.options.retry
        last_exc: Exception | None = None
        for attempt in range(1, policy.attempts + 1):
            try:
                return await destination.write(batch)
            except (asyncio.CancelledError, DestinationWriteError):
                raise  # cancelled, or the destination said retrying is pointless
            except Exception as exc:  # noqa: BLE001 - retried
                last_exc = exc
                logger.warning(
                    "write of %s batch %d failed (attempt %d/%d): %s",
                    batch.stream,
                    batch.batch_index,
                    attempt,
                    policy.attempts,
                    exc,
                )
                if attempt < policy.attempts:
                    await asyncio.sleep(policy.delay(attempt))
        raise DestinationWriteError(
            f"batch {batch.batch_index} of stream '{batch.stream}' failed after "
            f"{policy.attempts} attempts: {last_exc}"
        ) from last_exc

    async def _heartbeat(self, job: Job, run: asyncio.Task[Any]) -> None:
        """Keep ``heartbeat_at`` fresh while a slow source produces no batches.

        A beat the store refuses is logged and the next one is tried: the job goes
        on, and a heartbeat that stays silent is exactly what tells a sibling the
        job is in trouble. A beat the store refuses because the job was ended by
        a sibling (this worker was declared dead) stops ``run``: two workers must
        not write the same connection.
        """
        while True:
            await asyncio.sleep(self.options.heartbeat_interval_seconds)
            if job.is_terminal:
                return
            try:
                await self._persist(job, notify=False)
            except JobTakenOverError:
                self._taken_over.add(job.id)
                run.cancel()
                return
            except Exception:  # noqa: BLE001 - one missed beat is not the end of the job
                logger.warning("heartbeat of job %s could not be stored", job.id, exc_info=True)

    async def _persist(self, job: Job, *, notify: bool = True) -> None:
        job.heartbeat_at = utcnow()
        await self.job_store.update(job)
        if not notify:
            return
        await self._report_status(job)
        await self._call_hook(self.options.progress_hook, job)

    async def _report_status(self, job: Job) -> None:
        """Tell the status hook about ``job``, once per status it reaches."""
        if self._reported.get(job.id) is job.status:
            return
        self._reported[job.id] = job.status
        await self._call_hook(self.options.status_hook, job)

    @staticmethod
    async def _call_hook(hook: JobHook | None, job: Job) -> None:
        if hook is None:
            return
        try:
            await hook(job)
        except Exception:  # noqa: BLE001 - observers must not fail the sync
            logger.exception("sync hook failed for job %s", job.id)
