"""Owns chat-run execution so a run outlives the HTTP request that started it.

The run is an asyncio task held by this supervisor; HTTP handlers only read the
event log. A lease heartbeat proves liveness to other instances and carries
remote cancel requests back to this process.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol
import uuid

from core.observability.logger import get_logger
from service.chat_runs.domain import (
    ChatRun,
    ChatRunSpec,
    ChatRunUnavailableError,
    RunAlreadyActiveError,
    RunStatus,
    SupervisorShuttingDownError,
)
from service.chat_runs.frames import (
    DONE_PAYLOAD,
    error_code_of,
    extract_payload,
    is_content_delta,
    run_started_payload,
)
from service.chat_runs.orphans import close_event_log, finalize_orphan
from service.chat_runs.ports import (
    ChatRunMetrics,
    Clock,
    NoopChatRunMetrics,
    RunEventLog,
    RunRegistry,
    SystemClock,
    bounded_reason,
)
from service.chat_runs.settings import ChatRunSettings

logger = get_logger(__name__)

FrameSource = Callable[[], AsyncGenerator[str, None]]


class RunCompletionHook(Protocol):
    async def on_run_completed(self, run: ChatRun) -> None: ...


class _StopReason(Enum):
    CANCELLED = (RunStatus.CANCELLED, None)
    SHUTDOWN = (RunStatus.INTERRUPTED, "shutdown")
    LEASE_LOST = (RunStatus.INTERRUPTED, "lease_lost")


@dataclass
class _LiveRun:
    run: ChatRun
    task: asyncio.Task[None] | None = None
    stop_reason: _StopReason | None = None
    hard_cancel: asyncio.TimerHandle | None = None
    last_seq: int = 1
    # Run-scoped cooperative cancel, handed to the generator (see bind_cancel_event).
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class ChatRunSupervisor:
    def __init__(
        self,
        *,
        registry: RunRegistry,
        event_log: RunEventLog,
        settings: ChatRunSettings,
        instance_id: str,
        clock: Clock | None = None,
        hooks: Sequence[RunCompletionHook] = (),
        local_cancel: Callable[[str], object] | None = None,
        bind_cancel_event: Callable[[asyncio.Event], object] | None = None,
        new_run_id: Callable[[], str] | None = None,
        metrics: ChatRunMetrics | None = None,
    ) -> None:
        self._registry = registry
        self._log = event_log
        self._settings = settings
        self._instance_id = instance_id
        self._clock = clock or SystemClock()
        self._hooks = tuple(hooks)
        self._local_cancel = local_cancel or (lambda _thread_id: None)
        self._bind_cancel_event = bind_cancel_event or (lambda _event: None)
        self._metrics = metrics or NoopChatRunMetrics()
        self._last_stall_warning = float("-inf")
        self._new_run_id = new_run_id or (lambda: uuid.uuid4().hex)
        self._runs: dict[str, _LiveRun] = {}
        self._background: set[asyncio.Task[Any]] = set()
        self._accepting = True

    def active_run_ids(self) -> frozenset[str]:
        return frozenset(self._runs)

    @property
    def request_cancel_ttl_seconds(self) -> int:
        return self._settings.replay_ttl_seconds

    async def start(self, spec: ChatRunSpec, frames: FrameSource) -> ChatRun:
        if not self._accepting:
            raise SupervisorShuttingDownError("chat-run supervisor is shutting down")
        run = ChatRun.start(run_id=self._new_run_id(), spec=spec, instance_id=self._instance_id, now=self._clock.now())
        try:
            result = await self._registry.try_acquire(
                run,
                lease_ttl_seconds=self._settings.lease_ttl_seconds,
                run_ttl_seconds=self._settings.max_duration_seconds + self._settings.replay_ttl_seconds,
            )
        except Exception as exc:
            raise ChatRunUnavailableError("chat-run registry unavailable") from exc
        if not result.acquired:
            raise RunAlreadyActiveError(result.holder_run_id or "")
        if result.reclaimed_run_id:
            await self._finalize_reclaimed(result.reclaimed_run_id)
        try:
            await self._log.append(run.run_id, 1, run_started_payload(run.run_id, run.thread_id))
            await self._log.expire(run.run_id, self._settings.max_duration_seconds + self._settings.replay_ttl_seconds)
        except Exception as exc:
            await self._abort_start(run)
            raise ChatRunUnavailableError("chat-run event log unavailable") from exc
        stop_requested = await self._stop_requested_before_start(run)
        # No await from here to create_task: shutdown() snapshots the live runs
        # synchronously, so a run that passes this check is always in that
        # snapshot, and one that fails it is rolled back instead of started.
        if not self._accepting:
            await self._abort_start(run, error_code="shutdown")
            raise SupervisorShuttingDownError("chat-run supervisor is shutting down")
        live = _LiveRun(run=run)
        self._runs[run.run_id] = live
        if stop_requested:
            # A Stop landed before this run existed: never start the agent.
            live.stop_reason = _StopReason.CANCELLED
        # create_task copies the request's contextvars (correlation id, auth context).
        live.task = asyncio.create_task(self._drive(live, frames), name=f"chat-run:{run.run_id}")
        self._metrics.run_started()
        logger.info(
            "Chat run started",
            extra={"event": "chat_run.started", "run_id": run.run_id, "thread_id": run.thread_id},
        )
        return run

    async def _stop_requested_before_start(self, run: ChatRun) -> bool:
        try:
            if run.client_request_id and await self._registry.is_request_cancelled(
                run.thread_id, run.client_request_id
            ):
                return True
            return await self._registry.is_cancel_requested(run.run_id)
        except Exception:
            # The heartbeat re-checks the run's cancel flag once it is running.
            logger.warning("Could not check pending stops for chat run %s", run.run_id, exc_info=True)
            return False

    async def _finalize_reclaimed(self, run_id: str) -> None:
        try:
            if await finalize_orphan(
                run_id=run_id,
                registry=self._registry,
                event_log=self._log,
                settings=self._settings,
                clock=self._clock,
            ):
                self._metrics.run_finished(RunStatus.INTERRUPTED, "worker_lost")
        except Exception:
            logger.exception("Could not finalize reclaimed chat run %s", run_id)

    async def _abort_start(self, run: ChatRun, *, error_code: str = "event_log_unavailable") -> None:
        try:
            await self._registry.mark_terminal(
                run.run_id,
                RunStatus.FAILED,
                error_code=error_code,
                finished_at=self._clock.now(),
            )
            await self._registry.release(run)
            await self._registry.expire(run.run_id, self._settings.replay_ttl_seconds)
            await self._log.expire(run.run_id, self._settings.replay_ttl_seconds)
        except Exception:
            logger.exception("Could not roll back chat run %s", run.run_id)

    async def _drive(self, live: _LiveRun, frames: FrameSource) -> None:
        run_id = live.run.run_id
        status, error_code = RunStatus.COMPLETED, None
        heartbeat = asyncio.create_task(self._heartbeat(live), name=f"chat-run-lease:{run_id}")
        try:
            if live.stop_reason is None:
                # This task iterates the generator, so its register_run sees the binding.
                self._bind_cancel_event(live.cancel_event)
                async with asyncio.timeout(self._settings.max_duration_seconds):
                    status, error_code = await self._drive_frames(live, frames)
        except TimeoutError:
            status, error_code = RunStatus.FAILED, "run_timeout"
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None:
                current.uncancel()
            status, error_code = RunStatus.INTERRUPTED, "cancelled"
        except Exception:
            logger.exception("Chat run %s failed", run_id)
            status, error_code = RunStatus.FAILED, "internal_error"
        finally:
            heartbeat.cancel()
            if live.hard_cancel is not None:
                live.hard_cancel.cancel()
        if live.stop_reason is not None:
            status, error_code = live.stop_reason.value
        # _finalize must survive a *second* cancellation of this drive task
        # (e.g. shutdown()'s own grace-wait, or a racing cancel()) landing
        # while it is still in flight. asyncio.shield only protects an inner
        # future from the cancellation of the *outer* await -- if the coroutine
        # passed to shield() is never turned into a task anyone tracks, that
        # second cancellation makes this await raise immediately while
        # _finalize keeps running unobserved, and shutdown() can return before
        # it has actually written terminal frames or released the lock. Track
        # it in self._background, the same set _spawn()'s hooks use, so the
        # final `await asyncio.wait(self._background, ...)` in shutdown() still
        # covers it even if this await gets cancelled out from under it.
        finalize_task = self._spawn(self._finalize(live, status, error_code))
        await asyncio.shield(finalize_task)

    async def _drive_frames(self, live: _LiveRun, frames: FrameSource) -> tuple[RunStatus, str | None]:
        run_id = live.run.run_id
        status, error_code = RunStatus.COMPLETED, None
        async with aclosing(frames()) as frame_iter:
            async for frame in frame_iter:
                payload = extract_payload(frame)
                if payload is None or payload == DONE_PAYLOAD:
                    continue  # [DONE] is re-appended last by _finalize, exactly once
                if live.stop_reason is not None and is_content_delta(payload):
                    # Once a stop is recorded no viewer sees another token, even
                    # while the generator winds down or ignores the cancel.
                    continue
                live.last_seq += 1
                await self._log.append(run_id, live.last_seq, payload)
                code = error_code_of(payload)
                if code is not None:
                    status, error_code = RunStatus.FAILED, code
        return status, error_code

    async def _finalize(self, live: _LiveRun, status: RunStatus, error_code: str | None) -> None:
        run = live.run
        won = False
        try:
            won = await self._registry.mark_terminal(
                run.run_id, status, error_code=error_code, finished_at=self._clock.now()
            )
            if won:
                try:
                    await close_event_log(self._log, run.run_id, status, error_code)
                finally:
                    # Shorten the keys to the replay window even when the
                    # terminal frames could not be written.
                    await self._log.expire(run.run_id, self._settings.replay_ttl_seconds)
                    await self._registry.expire(run.run_id, self._settings.replay_ttl_seconds)
        except Exception:
            logger.exception("Could not finalize chat run %s", run.run_id)
        # Release must be attempted regardless of what failed above: once the run
        # is marked terminal (or an attempt was made), the thread lock must not be
        # left held forever waiting on a reaper that will skip an already-terminal run.
        try:
            await self._registry.release(run)
        except Exception:
            logger.exception("Could not release chat run %s", run.run_id)
        finally:
            self._runs.pop(run.run_id, None)
            self._metrics.run_ended()
        if won:
            self._metrics.run_finished(status, bounded_reason(error_code))
        logger.info(
            "Chat run finished",
            extra={
                "event": "chat_run.finished",
                "run_id": run.run_id,
                "status": status.value,
                "error_code": error_code,
                "recorded": won,
            },
        )
        if won and status is RunStatus.COMPLETED:
            try:
                finished = await self._registry.get(run.run_id) or run
                for hook in self._hooks:
                    self._spawn(self._run_hook(hook, finished))
            except Exception:
                logger.exception("Could not dispatch completion hooks for chat run %s", run.run_id)

    async def _heartbeat(self, live: _LiveRun) -> None:
        run_id = live.run.run_id
        loop = asyncio.get_running_loop()
        while True:
            due = loop.time() + self._settings.heartbeat_seconds
            await asyncio.sleep(self._settings.heartbeat_seconds)
            self._observe_heartbeat_lag(max(0.0, loop.time() - due))
            try:
                renewed = await self._registry.renew_lease(
                    run_id, self._instance_id, lease_ttl_seconds=self._settings.lease_ttl_seconds
                )
                if not renewed:
                    logger.warning("Chat run lost its lease", extra={"event": "chat_run.lease_lost", "run_id": run_id})
                    self._stop(live, _StopReason.LEASE_LOST)
                    return
                # Keep renewing after a stop: the lease must outlive the cancel
                # grace and the generator's own cleanup, or the reaper would
                # close an explicit Stop as worker_lost.
                if live.stop_reason is None and await self._registry.is_cancel_requested(run_id):
                    self._stop(live, _StopReason.CANCELLED)
            except Exception:
                # Transient Redis failure: keep running; if it persists the lease
                # expires and the reaper closes the run.
                logger.warning("Chat run heartbeat failed for %s", run_id, exc_info=True)

    def _observe_heartbeat_lag(self, lag: float) -> None:
        self._metrics.heartbeat_lag(lag)
        # Every run on this instance shares one event loop: a stall longer than
        # the lease lets other instances reap all of them. Warn well before
        # that, at most every 30 s per instance.
        if lag < self._settings.heartbeat_seconds:
            return
        now = self._clock.now()
        if now - self._last_stall_warning < 30:
            return
        self._last_stall_warning = now
        logger.warning(
            "Chat-run event loop stalled for %.2fs (lease %.1fs); blocking code runs on the event loop",
            lag,
            self._settings.lease_ttl_seconds,
            extra={"event": "chat_run.event_loop_stall", "lag_seconds": round(lag, 3)},
        )

    def _stop(self, live: _LiveRun, reason: _StopReason) -> None:
        if live.stop_reason is not None or (live.task is not None and live.task.done()):
            return
        live.stop_reason = reason
        # Run-scoped, so it is safe for every reason; a generator that has not
        # registered yet finds it already set when it does.
        live.cancel_event.set()
        if live.task is None:
            return  # not started yet: _drive sees stop_reason and never runs the agent
        if reason is not _StopReason.LEASE_LOST:
            # Cooperative: message_generator breaks its loop. It is scoped to
            # the thread, so a run that lost its lease must not use it: a newer
            # run may already hold that thread on this instance.
            self._local_cancel(live.run.thread_id)
        grace = self._settings.cancel_grace_seconds if reason is _StopReason.CANCELLED else 0.0
        live.hard_cancel = asyncio.get_running_loop().call_later(grace, live.task.cancel)

    def cancel_local_for_thread(self, thread_id: str) -> bool:
        """Stop this instance's run of a thread without touching the registry."""
        cancelled = False
        for live in list(self._runs.values()):
            if live.run.thread_id == thread_id:
                self._stop(live, _StopReason.CANCELLED)
                cancelled = True
        return cancelled

    async def cancel(self, run_id: str) -> bool:
        live = self._runs.get(run_id)
        if live is not None:
            self._stop(live, _StopReason.CANCELLED)
        run = await self._registry.get(run_id)
        if run is None or run.status.is_terminal:
            return live is not None
        await self._registry.request_cancel(run_id, ttl_seconds=self._settings.replay_ttl_seconds)
        return True

    async def shutdown(self) -> None:
        self._accepting = False
        lives = list(self._runs.values())
        tasks = [live.task for live in lives if live.task is not None]
        if tasks:
            await asyncio.wait(tasks, timeout=self._settings.shutdown_grace_seconds)
            for live in lives:
                self._stop(live, _StopReason.SHUTDOWN)
            await asyncio.wait(tasks, timeout=self._settings.cancel_grace_seconds + 5)
        if self._background:
            await asyncio.wait(set(self._background), timeout=5)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def _run_hook(self, hook: RunCompletionHook, run: ChatRun) -> None:
        try:
            await hook.on_run_completed(run)
        except Exception:
            logger.exception(
                "Chat run completion hook failed",
                extra={"event": "chat_run.hook_failed", "hook": type(hook).__name__, "run_id": run.run_id},
            )
