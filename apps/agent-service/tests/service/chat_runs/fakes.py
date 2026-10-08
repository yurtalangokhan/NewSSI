"""In-memory adapters with the same observable behaviour as the Redis ones."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Collection

from service.chat_runs.domain import ChatRun, EventSequenceError, ReplayWindowExpiredError, RunEvent, RunStatus
from service.chat_runs.ports import AcquireResult
from service.chat_runs.settings import ChatRunSettings


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class InMemoryRunEventLog:
    def __init__(self, max_events: int = 50_000) -> None:
        self._max = max_events
        self._events: dict[str, list[RunEvent]] = {}
        self._last: dict[str, int] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self.expirations: dict[str, int] = {}

    def _condition(self, run_id: str) -> asyncio.Condition:
        return self._conditions.setdefault(run_id, asyncio.Condition())

    async def append(self, run_id: str, seq: int, payload: str) -> None:
        if seq < 1 or seq <= self._last.get(run_id, 0):
            raise EventSequenceError(run_id, seq)
        events = self._events.setdefault(run_id, [])
        events.append(RunEvent(seq, payload))
        self._last[run_id] = seq
        if len(events) > self._max:
            del events[: len(events) - self._max]
        condition = self._condition(run_id)
        async with condition:
            condition.notify_all()

    def _page(self, run_id: str, after_seq: int, limit: int) -> list[RunEvent]:
        page = [e for e in self._events.get(run_id, []) if e.seq > after_seq][:limit]
        if page and page[0].seq != after_seq + 1:
            raise ReplayWindowExpiredError(run_id, page[0].seq)
        return page

    async def read_after(
        self, run_id: str, after_seq: int, *, block_seconds: float = 0.0, limit: int = 500
    ) -> list[RunEvent]:
        page = self._page(run_id, after_seq, limit)
        if page or block_seconds <= 0:
            return page
        condition = self._condition(run_id)
        async with condition:
            try:
                await asyncio.wait_for(
                    condition.wait_for(lambda: self._last.get(run_id, 0) > after_seq),
                    block_seconds,
                )
            except TimeoutError:
                return []
        return self._page(run_id, after_seq, limit)

    async def last_seq(self, run_id: str) -> int:
        return self._last.get(run_id, 0)

    def events(self, run_id: str) -> list[RunEvent]:
        return list(self._events.get(run_id, []))

    async def expire(self, run_id: str, ttl_seconds: int) -> None:
        self.expirations[run_id] = ttl_seconds


class InMemoryRunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, ChatRun] = {}
        self.acquire_ttls: dict[str, float] = {}
        self._request_cancels: set[tuple[str, str]] = set()
        self._locks: dict[str, str] = {}
        self._leases: dict[str, tuple[str, float]] = {}
        self._cancel: set[str] = set()
        self._running: set[str] = set()
        self._mutex = asyncio.Lock()
        self.expirations: dict[str, int] = {}

    def _alive(self, run_id: str) -> bool:
        lease = self._leases.get(run_id)
        return lease is not None and lease[1] > time.monotonic()

    def expire_lease(self, run_id: str) -> None:
        if run_id in self._leases:
            self._leases[run_id] = (self._leases[run_id][0], 0.0)

    async def try_acquire(
        self, run: ChatRun, *, lease_ttl_seconds: float, run_ttl_seconds: float | None = None
    ) -> AcquireResult:
        async with self._mutex:
            current = self._locks.get(run.thread_id)
            if current is not None and self._alive(current):
                return AcquireResult(False, holder_run_id=current)
            self._locks[run.thread_id] = run.run_id
            self._leases[run.run_id] = (run.instance_id, time.monotonic() + lease_ttl_seconds)
            self._runs[run.run_id] = run
            self._running.add(run.run_id)
            if run_ttl_seconds is not None:
                self.acquire_ttls[run.run_id] = run_ttl_seconds
            return AcquireResult(True, reclaimed_run_id=current)

    async def get(self, run_id: str) -> ChatRun | None:
        return self._runs.get(run_id)

    async def get_active_for_thread(self, thread_id: str) -> ChatRun | None:
        run = self._runs.get(self._locks.get(thread_id, ""))
        if run is None or run.status.is_terminal or not self._alive(run.run_id):
            return None
        return run

    async def active_runs_for_threads(self, thread_ids: Collection[str]) -> dict[str, ChatRun]:
        active: dict[str, ChatRun] = {}
        for thread_id in dict.fromkeys(thread_ids):
            run = await self.get_active_for_thread(thread_id)
            if run is not None:
                active[run.thread_id] = run
        return active

    async def renew_lease(self, run_id: str, instance_id: str, *, lease_ttl_seconds: float) -> bool:
        lease = self._leases.get(run_id)
        if lease is None or lease[0] != instance_id or not self._alive(run_id):
            return False
        self._leases[run_id] = (instance_id, time.monotonic() + lease_ttl_seconds)
        return True

    async def has_live_lease(self, run_id: str) -> bool:
        return self._alive(run_id)

    async def mark_terminal(
        self, run_id: str, status: RunStatus, *, error_code: str | None, finished_at: float
    ) -> bool:
        async with self._mutex:
            run = self._runs.get(run_id)
            if run is None or run.status.is_terminal:
                return False
            self._runs[run_id] = run.finish(status, error_code=error_code, now=finished_at)
            self._running.discard(run_id)
            return True

    async def release(self, run: ChatRun) -> None:
        if self._locks.get(run.thread_id) == run.run_id:
            del self._locks[run.thread_id]
        self._leases.pop(run.run_id, None)

    async def request_cancel(self, run_id: str, *, ttl_seconds: int) -> None:
        self._cancel.add(run_id)

    async def is_cancel_requested(self, run_id: str) -> bool:
        return run_id in self._cancel

    async def request_cancel_for_request(self, thread_id: str, client_request_id: str, *, ttl_seconds: int) -> None:
        self._request_cancels.add((thread_id, client_request_id))

    async def is_request_cancelled(self, thread_id: str, client_request_id: str) -> bool:
        return (thread_id, client_request_id) in self._request_cancels

    async def running_run_ids(self) -> list[str]:
        return sorted(self._running)

    async def expire(self, run_id: str, ttl_seconds: int) -> None:
        self.expirations[run_id] = ttl_seconds


def fast_settings(**overrides) -> ChatRunSettings:
    values = dict(
        replay_ttl_seconds=600,
        lease_ttl_seconds=0.3,
        heartbeat_seconds=0.05,
        max_events=1000,
        cancel_grace_seconds=0.1,
        shutdown_grace_seconds=0.2,
        reaper_interval_seconds=0.05,
        max_duration_seconds=5,
        sse_heartbeat_seconds=0.2,
    )
    values.update(overrides)
    return ChatRunSettings(**values)


def frames_of(*payloads: str, delay: float = 0.0):
    async def source():
        for payload in payloads:
            if delay:
                await asyncio.sleep(delay)
            yield payload if payload.startswith(":") else f"data: {payload}\n\n"

    return source


async def wait_terminal(registry, run_id: str, timeout: float = 3.0):
    async def poll():
        while True:
            run = await registry.get(run_id)
            if run is not None and run.status.is_terminal:
                return run
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(poll(), timeout)


class FailingEventLog(InMemoryRunEventLog):
    async def append(self, run_id, seq, payload):
        raise ConnectionError("redis down")


def build_in_memory_chat_runs(**settings):
    from types import SimpleNamespace

    from service.chat_runs.reader import RunEventReader
    from service.chat_runs.service import ChatRunService
    from service.chat_runs.supervisor import ChatRunSupervisor

    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    resolved = fast_settings(**settings)
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=log, settings=resolved, instance_id="test"
    )
    reader = RunEventReader(
        registry=registry, event_log=log, settings=resolved, poll_interval_seconds=0.02
    )
    service = ChatRunService(supervisor=supervisor, reader=reader, registry=registry)
    return SimpleNamespace(service=service, supervisor=supervisor, registry=registry, log=log)


def use_in_memory_chat_runs(monkeypatch, **settings):
    from service.chat_runs import provider

    runtime = build_in_memory_chat_runs(**settings)
    monkeypatch.setattr(provider, "_service", runtime.service)
    return runtime
