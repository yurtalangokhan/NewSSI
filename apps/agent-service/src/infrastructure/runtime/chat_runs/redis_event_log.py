"""Redis Streams event log. Entry ids are ``0-<seq>`` so the SSE id is the seq."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from infrastructure.runtime.chat_runs.keys import events_key
from service.chat_runs.domain import EventSequenceError, ReplayWindowExpiredError, RunEvent

_FIELD = "d"


def _seq_of(entry_id: str) -> int:
    return int(entry_id.split("-", 1)[1])


def _xread_entries(result: Any, key: str) -> list[Any]:
    if not result:
        return []
    if isinstance(result, dict):  # RESP3
        entries = result.get(key) or []
        return entries[0] if entries and isinstance(entries[0], list) else entries
    for stream_key, entries in result:
        if stream_key == key:
            return entries
    return []


class _PipelineBatcher:
    """Sends commands issued concurrently by many runs in one pipeline.

    Every token is one XADD and every viewer poll one XRANGE; issued one by one,
    a replica streaming many runs spends its CPU on per-command overhead.
    Commands queued while a pipeline is in flight go out together in the next
    one, so there is no added latency when idle and fewer round trips under
    load. A caller awaits only its own command's result or error.
    """

    def __init__(self, client: Redis, *, max_batch: int = 500) -> None:
        self._client = client
        self._max_batch = max_batch
        self._pending: list[tuple[Callable[[Any], Any], asyncio.Future[Any]]] = []
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def run(self, command: Callable[[Any], Any]) -> Any:
        loop = asyncio.get_running_loop()
        if self._task is None or self._task.done() or self._loop is not loop:
            self._loop = loop
            self._pending = []
            self._wakeup = asyncio.Event()
            self._task = loop.create_task(self._flush_forever(), name="chat-run-redis-batcher")
        future: asyncio.Future[Any] = loop.create_future()
        self._pending.append((command, future))
        self._wakeup.set()
        return await future

    async def _flush_forever(self) -> None:
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            while self._pending:
                batch, self._pending = self._pending[: self._max_batch], self._pending[self._max_batch :]
                await self._flush(batch)

    async def _flush(self, batch: list[tuple[Callable[[Any], Any], asyncio.Future[Any]]]) -> None:
        live = [(command, future) for command, future in batch if not future.done()]
        if not live:
            return
        pipe = self._client.pipeline(transaction=False)
        for command, _ in live:
            command(pipe)
        try:
            results = await pipe.execute(raise_on_error=False)
        except Exception as exc:  # the whole round trip failed (connection, pool)
            for _, future in live:
                if not future.done():
                    future.set_exception(exc)
            return
        for (_, future), result in zip(live, results, strict=True):
            if future.done():
                continue  # the caller was cancelled (hard stop); its result is moot
            if isinstance(result, Exception):
                future.set_exception(result)
            else:
                future.set_result(result)

    async def aclose(self) -> None:
        if self._task is not None and self._loop is asyncio.get_running_loop():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        for _, future in self._pending:
            if not future.done():
                future.cancel()
        self._pending = []


class RedisRunEventLog:
    def __init__(self, client: Redis, *, max_events: int, approximate_trim: bool = True) -> None:
        self._client = client
        self._max_events = max_events
        self._approximate = approximate_trim
        self._batcher = _PipelineBatcher(client)

    async def append(self, run_id: str, seq: int, payload: str) -> None:
        key = events_key(run_id)
        try:
            await self._batcher.run(
                lambda pipe: pipe.xadd(
                    key,
                    {_FIELD: payload},
                    id=f"0-{seq}",
                    maxlen=self._max_events,
                    approximate=self._approximate,
                )
            )
        except ResponseError as exc:
            if "equal or smaller" in str(exc) or "0-0" in str(exc):
                raise EventSequenceError(run_id, seq) from exc
            raise

    async def read_after(
        self, run_id: str, after_seq: int, *, block_seconds: float = 0.0, limit: int = 500
    ) -> list[RunEvent]:
        key = events_key(run_id)
        entries = await self._batcher.run(lambda pipe: pipe.xrange(key, min=f"(0-{after_seq}", max="+", count=limit))
        if not entries and block_seconds > 0:
            result = await self._client.xread(
                {key: f"0-{after_seq}"}, count=limit, block=max(1, int(block_seconds * 1000))
            )
            entries = _xread_entries(result, key)
        events = [RunEvent(_seq_of(entry_id), fields[_FIELD]) for entry_id, fields in entries]
        # Seqs are contiguous by construction, so a gap can only mean trimming.
        if events and events[0].seq != after_seq + 1:
            raise ReplayWindowExpiredError(run_id, events[0].seq)
        return events

    async def last_seq(self, run_id: str) -> int:
        entries = await self._client.xrevrange(events_key(run_id), max="+", min="-", count=1)
        return _seq_of(entries[0][0]) if entries else 0

    async def expire(self, run_id: str, ttl_seconds: int) -> None:
        await self._client.expire(events_key(run_id), int(ttl_seconds))

    async def aclose(self) -> None:
        await self._batcher.aclose()
