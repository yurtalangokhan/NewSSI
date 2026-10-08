"""Many users at once against a real Redis: concurrent runs, viewers and a reconnect storm.

Opt-in: ``CHAT_RUNS_LOAD_REDIS_URL=redis://:<password>@localhost:6379/15``. Use a
logical database nothing else writes to; the test deletes only the keys it created.
Tune the scale with ``CHAT_RUNS_LOAD_RUNS``, ``CHAT_RUNS_LOAD_VIEWERS`` and
``CHAT_RUNS_LOAD_TOKENS``. The report is printed with ``-s``.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest
import redis.asyncio as aioredis

from infrastructure.runtime.chat_runs.keys import (
    RUNNING_SET_KEY,
    cancel_key,
    events_key,
    lease_key,
    run_key,
    thread_lock_key,
)
from infrastructure.runtime.chat_runs.redis_event_log import RedisRunEventLog
from infrastructure.runtime.chat_runs.redis_run_registry import RedisRunRegistry
from infrastructure.runtime.chat_runs.wiring import (
    READER_POOL_SIZE,
    READER_POOL_WAIT_SECONDS,
    WRITER_POOL_SIZE,
    WRITER_POOL_WAIT_SECONDS,
    _dedicated_client,
)
from service.chat_runs.domain import ChatRunSpec, RunStatus
from service.chat_runs.reader import RunEventReader
from service.chat_runs.settings import ChatRunSettings
from service.chat_runs.supervisor import ChatRunSupervisor

REDIS_URL = os.environ.get("CHAT_RUNS_LOAD_REDIS_URL")
RUNS = int(os.environ.get("CHAT_RUNS_LOAD_RUNS", "200"))
VIEWERS = int(os.environ.get("CHAT_RUNS_LOAD_VIEWERS", "2"))
TOKENS = int(os.environ.get("CHAT_RUNS_LOAD_TOKENS", "300"))
POLL = float(os.environ.get("CHAT_RUNS_LOAD_POLL_SECONDS", "0")) or None
# Seconds between tokens per run: 0.02 is ~50 tokens/s, a fast LLM.
TOKEN_INTERVAL = float(os.environ.get("CHAT_RUNS_LOAD_TOKEN_INTERVAL", "0.02"))

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not REDIS_URL, reason="set CHAT_RUNS_LOAD_REDIS_URL to run the load test"),
]


class _LagRecorder:
    def __init__(self) -> None:
        self.lags: list[float] = []
        self.finished: list[tuple[RunStatus, str]] = []
        self.streams = 0
        self.max_streams = 0

    def run_started(self) -> None: ...

    def run_ended(self) -> None: ...

    def run_finished(self, status: RunStatus, reason: str) -> None:
        self.finished.append((status, reason))

    def heartbeat_lag(self, seconds: float) -> None:
        self.lags.append(seconds)

    def stream_opened(self) -> None:
        self.streams += 1
        self.max_streams = max(self.max_streams, self.streams)

    def stream_closed(self) -> None:
        self.streams -= 1


def _tokens(count: int):
    async def source():
        for i in range(count):
            yield f'data: {{"type": "token", "content": "{i} "}}\n\n'
            await asyncio.sleep(TOKEN_INTERVAL)
        yield "data: [DONE]\n\n"

    return source


class _Viewer:
    """A browser tab: delivers each seq once across re-attaches, like the web client."""

    def __init__(self, reader: RunEventReader, run_id: str) -> None:
        self._reader = reader
        self._run_id = run_id
        self.delivered: list[int] = []
        self.attaches = 0

    async def watch(self) -> None:
        self.attaches += 1
        delivered_through = self.delivered[-1] if self.delivered else 0
        async for frame in self._reader.stream(self._run_id, 0):  # full replay (D10)
            if not frame.startswith("id: "):
                continue
            seq = int(frame.split("\n", 1)[0][4:])
            if seq > delivered_through:
                self.delivered.append(seq)
                delivered_through = seq


async def _sample_clients(client: aioredis.Redis, peak: list[int], stop: asyncio.Event) -> None:
    while not stop.is_set():
        info = await client.info("clients")
        peak[0] = max(peak[0], int(info["connected_clients"]))
        await asyncio.sleep(0.1)


async def test_many_users_with_a_reconnect_storm():
    # Connected like production: a shared client, and the chat-run writer and
    # reader pools derived from it.
    shared = aioredis.Redis.from_url(
        REDIS_URL, decode_responses=True, socket_timeout=2.0, socket_connect_timeout=2.0
    )
    client = _dedicated_client(shared, WRITER_POOL_SIZE, WRITER_POOL_WAIT_SECONDS)
    reader_client = _dedicated_client(shared, READER_POOL_SIZE, READER_POOL_WAIT_SECONDS)
    probe = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    settings = ChatRunSettings(
        replay_ttl_seconds=600,
        lease_ttl_seconds=10,
        heartbeat_seconds=2,
        max_events=50_000,
        cancel_grace_seconds=5,
        shutdown_grace_seconds=20,
        reaper_interval_seconds=10,
        max_duration_seconds=600,
        sse_heartbeat_seconds=15,
    )
    metrics = _LagRecorder()
    registry = RedisRunRegistry(client)
    log = RedisRunEventLog(client, max_events=settings.max_events)
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=log, settings=settings, instance_id="load", metrics=metrics
    )
    reader_log = RedisRunEventLog(reader_client, max_events=settings.max_events)
    reader = RunEventReader(
        registry=RedisRunRegistry(reader_client),
        event_log=reader_log,
        settings=settings,
        metrics=metrics,
        **({"poll_interval_seconds": POLL} if POLL else {}),
    )
    prefix = f"load-{uuid.uuid4().hex[:8]}"
    run_ids: list[str] = []
    peak_clients = [0]
    stop_sampling = asyncio.Event()
    sampler = asyncio.create_task(_sample_clients(probe, peak_clients, stop_sampling))
    started = time.monotonic()
    try:
        started_runs = await asyncio.gather(
            *(
                supervisor.start(ChatRunSpec(thread_id=f"{prefix}-t{i}", owner_user_id=f"u{i}"), _tokens(TOKENS))
                for i in range(RUNS)
            ),
            return_exceptions=True,
        )
        run_ids = [run.run_id for run in started_runs if not isinstance(run, BaseException)]
        failures = [run for run in started_runs if isinstance(run, BaseException)]
        if failures:
            raise failures[0]
        viewers = [_Viewer(reader, run_id) for run_id in run_ids for _ in range(VIEWERS)]

        # Everyone watches, then every connection drops at the same moment
        # (a deploy, a network blip) and all tabs re-attach with a full replay.
        first = [asyncio.create_task(v.watch()) for v in viewers]
        await asyncio.sleep(TOKENS * TOKEN_INTERVAL / 3)
        for task in first:
            task.cancel()
        await asyncio.gather(*first, return_exceptions=True)
        storm_at = time.monotonic()
        await asyncio.gather(*(v.watch() for v in viewers))
        replay_done = time.monotonic()

        async def _terminal(run_id):
            while True:
                run = await registry.get(run_id)
                if run is not None and run.status.is_terminal:
                    return run
                await asyncio.sleep(0.2)

        finals = await asyncio.wait_for(asyncio.gather(*(_terminal(r) for r in run_ids)), 600)
        last_seqs = {run_id: await log.last_seq(run_id) for run_id in run_ids}
    finally:
        stop_sampling.set()
        await sampler
        await supervisor.shutdown()
        await log.aclose()
        await reader_log.aclose()
        keys = [
            key
            for run_id in run_ids
            for key in (run_key(run_id), events_key(run_id), lease_key(run_id), cancel_key(run_id))
        ] + [thread_lock_key(f"{prefix}-t{i}") for i in range(RUNS)]
        for chunk in range(0, len(keys), 500):
            await client.delete(*keys[chunk : chunk + 500])
        if run_ids:
            await client.srem(RUNNING_SET_KEY, *run_ids)
        await client.aclose()
        await reader_client.aclose()
        await shared.aclose()
        await probe.aclose()

    durations = sorted(run.finished_at - run.started_at for run in finals)
    lags = sorted(metrics.lags)
    p99 = lags[int(len(lags) * 0.99) - 1] if lags else 0.0
    print(
        f"\n[load] runs={RUNS} viewers={len(viewers)} tokens/run={TOKENS} "
        f"nominal_run={TOKENS * TOKEN_INTERVAL:.1f}s run_p50={durations[len(durations) // 2]:.1f}s "
        f"run_max={durations[-1]:.1f}s storm_replay={replay_done - storm_at:.1f}s "
        f"heartbeat_lag p99={p99:.3f}s max={lags[-1] if lags else 0:.3f}s "
        f"peak_redis_clients={peak_clients[0]} peak_open_streams={metrics.max_streams}"
    )

    # Every run finished on its own: no lease was lost under load.
    assert all(run is not None and run.status is RunStatus.COMPLETED for run in finals)
    # Every tab saw its run exactly once, in order, with nothing missing.
    for viewer in viewers:
        assert viewer.delivered == list(range(1, last_seqs[viewer._run_id] + 1))
    # The event loop kept up with every heartbeat, far from the lease.
    assert lags and lags[-1] < settings.lease_ttl_seconds / 2
