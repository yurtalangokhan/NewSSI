"""Subscribes an HTTP client to a run's event log: replay, live tail, heartbeat.

Closing this generator (client gone) never touches the run itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from service.chat_runs.domain import ReplayWindowExpiredError, RunStatus
from service.chat_runs.frames import (
    DONE_PAYLOAD,
    HEARTBEAT_FRAME,
    caught_up_payload,
    format_event,
    format_unsequenced,
    is_run_end,
    resync_payload,
    run_end_payload,
)
from service.chat_runs.ports import ChatRunMetrics, Clock, NoopChatRunMetrics, RunEventLog, RunRegistry, SystemClock
from service.chat_runs.settings import ChatRunSettings

# Readers poll the log instead of blocking on it: a blocking XREAD pins one
# pooled Redis connection per open stream, and a replica with a few hundred
# viewers would exhaust the pool that also writes tokens and renews leases.
# A poll holds a connection only for the command itself. The interval resets
# when events arrive and backs off while the run is quiet (a long tool call).
DEFAULT_POLL_INTERVAL_SECONDS = 0.05
DEFAULT_MAX_POLL_INTERVAL_SECONDS = 0.5
# How often a quiet stream asks the registry whether its run ended without a
# run_end frame (crash between steps, expired meta).
TERMINAL_CHECK_INTERVAL_SECONDS = 1.0


class RunEventReader:
    def __init__(
        self,
        *,
        registry: RunRegistry,
        event_log: RunEventLog,
        settings: ChatRunSettings,
        clock: Clock | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        max_poll_interval_seconds: float = DEFAULT_MAX_POLL_INTERVAL_SECONDS,
        # Replay pages stay small so one tab replaying a long run holds a
        # connection only briefly and many tabs replaying at once take turns.
        batch_size: int = 200,
        metrics: ChatRunMetrics | None = None,
    ) -> None:
        self._registry = registry
        self._log = event_log
        self._settings = settings
        self._clock = clock or SystemClock()
        self._poll_interval = poll_interval_seconds
        self._max_poll_interval = max(max_poll_interval_seconds, poll_interval_seconds)
        self._batch_size = batch_size
        self._metrics = metrics or NoopChatRunMetrics()

    async def stream(self, run_id: str, after_seq: int = 0) -> AsyncIterator[str]:
        # Each open stream holds a Redis connection while it blocks on the tail.
        self._metrics.stream_opened()
        try:
            async for frame in self._stream(run_id, after_seq):
                yield frame
        finally:
            self._metrics.stream_closed()

    async def _stream(self, run_id: str, after_seq: int) -> AsyncIterator[str]:
        last = after_seq
        idle_since = self._clock.now()
        interval = self._poll_interval
        loop = asyncio.get_running_loop()
        next_terminal_check = loop.time()
        # Set once the log has nothing after `last`: everything before it was
        # replay, everything after it is the live tail.
        caught_up = False
        while True:
            try:
                events = await self._log.read_after(run_id, last, limit=self._batch_size)
            except ReplayWindowExpiredError as exc:
                yield format_unsequenced(resync_payload(exc.first_seq))
                return
            if events:
                for event in events:
                    last = event.seq
                    yield format_event(event.seq, event.payload)
                    if event.payload == DONE_PAYLOAD:
                        return
                idle_since = self._clock.now()
                interval = self._poll_interval
                continue
            if loop.time() >= next_terminal_check:
                next_terminal_check = loop.time() + TERMINAL_CHECK_INTERVAL_SECONDS
                synthetic = await self._synthetic_end(run_id)
                if synthetic is not None:
                    for payload in synthetic:
                        yield format_unsequenced(payload)
                    return
            if not caught_up:
                caught_up = True
                yield format_unsequenced(caught_up_payload())
            now = self._clock.now()
            if now - idle_since >= self._settings.sse_heartbeat_seconds:
                idle_since = now
                yield HEARTBEAT_FRAME
            await asyncio.sleep(interval)
            interval = min(interval * 2, self._max_poll_interval)

    async def _synthetic_end(self, run_id: str) -> list[str] | None:
        """Payloads that close a run whose writer will not: its run_end, then [DONE].

        The run_end is skipped when the log already ends with one, so a client
        never sees two (the writer appended run_end and died before [DONE]).
        """
        run = await self._registry.get(run_id)
        if run is None:
            end = run_end_payload(RunStatus.INTERRUPTED.value, "run_expired")
        elif not run.status.is_terminal:
            return None
        else:
            finished_at = run.finished_at if run.finished_at is not None else self._clock.now()
            # The owner marks terminal before appending run_end; give it time to land.
            if self._clock.now() - finished_at < 2 * self._settings.heartbeat_seconds:
                return None
            end = run_end_payload(run.status.value, run.error_code)
        if await self._log_ends_with_run_end(run_id):
            return [DONE_PAYLOAD]
        return [end, DONE_PAYLOAD]

    async def _log_ends_with_run_end(self, run_id: str) -> bool:
        last = await self._log.last_seq(run_id)
        if last < 1:
            return False
        try:
            tail = await self._log.read_after(run_id, last - 1, limit=1)
        except ReplayWindowExpiredError:
            return False
        return bool(tail) and is_run_end(tail[-1].payload)
