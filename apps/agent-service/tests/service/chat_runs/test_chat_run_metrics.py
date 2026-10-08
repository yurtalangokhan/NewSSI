"""Chat-run health signals: event-loop stalls, live runs and streams, end reasons."""

import asyncio
import logging
import time

import pytest

from service.chat_runs.domain import ChatRunSpec, RunStatus
from service.chat_runs.ports import bounded_reason
from service.chat_runs.reader import RunEventReader
from service.chat_runs.reaper import OrphanRunReaper
from service.chat_runs.supervisor import ChatRunSupervisor
from tests.service.chat_runs.run_registry_contract import make_run
from tests.service.chat_runs.fakes import (
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    fast_settings,
    frames_of,
    wait_terminal,
)

pytestmark = pytest.mark.asyncio
SPEC = ChatRunSpec(thread_id="t1", owner_user_id="u1")


class RecordingMetrics:
    def __init__(self) -> None:
        self.active = 0
        self.streams = 0
        self.finished: list[tuple[RunStatus, str]] = []
        self.lags: list[float] = []

    def run_started(self) -> None:
        self.active += 1

    def run_ended(self) -> None:
        self.active -= 1

    def run_finished(self, status: RunStatus, reason: str) -> None:
        self.finished.append((status, reason))

    def heartbeat_lag(self, seconds: float) -> None:
        self.lags.append(seconds)

    def stream_opened(self) -> None:
        self.streams += 1

    def stream_closed(self) -> None:
        self.streams -= 1


def _supervisor(metrics, registry=None, log=None, **settings):
    return ChatRunSupervisor(
        registry=registry or InMemoryRunRegistry(),
        event_log=log or InMemoryRunEventLog(),
        settings=fast_settings(**settings),
        instance_id="i1",
        metrics=metrics,
    )


async def test_live_runs_are_counted_until_they_end():
    metrics = RecordingMetrics()
    registry = InMemoryRunRegistry()
    supervisor = _supervisor(metrics, registry)
    run = await supervisor.start(SPEC, frames_of("{}", delay=0.1))
    assert metrics.active == 1
    await wait_terminal(registry, run.run_id)
    await asyncio.sleep(0.05)
    assert metrics.active == 0
    assert metrics.finished == [(RunStatus.COMPLETED, "none")]


async def test_a_blocked_event_loop_shows_up_as_heartbeat_lag_and_a_warning(caplog):
    # A synchronous tool blocks every run on the instance; if it lasts longer
    # than the lease, other instances reap them all. Make that visible.
    metrics = RecordingMetrics()
    registry = InMemoryRunRegistry()
    supervisor = _supervisor(metrics, registry, heartbeat_seconds=0.05, lease_ttl_seconds=5)

    async def blocking_tool():
        yield 'data: {"type": "token", "content": "."}\n\n'
        await asyncio.sleep(0.12)  # let the heartbeat arm its next tick
        time.sleep(0.3)
        await asyncio.sleep(0.1)  # the loop runs again: the late heartbeat fires
        yield "data: [DONE]\n\n"

    with caplog.at_level(logging.WARNING):
        run = await supervisor.start(SPEC, blocking_tool)
        await wait_terminal(registry, run.run_id)

    assert max(metrics.lags) >= 0.2
    assert any("event loop" in record.getMessage() for record in caplog.records)


async def test_open_event_streams_are_counted_and_released_on_disconnect():
    metrics = RecordingMetrics()
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    supervisor = _supervisor(metrics, registry, log)
    reader = RunEventReader(
        registry=registry, event_log=log, settings=fast_settings(), poll_interval_seconds=0.02, metrics=metrics
    )
    run = await supervisor.start(SPEC, frames_of("{}", delay=1.0))

    stream = reader.stream(run.run_id)
    await stream.__anext__()
    assert metrics.streams == 1
    await stream.aclose()  # the client went away
    assert metrics.streams == 0
    # The reader leaving never touches the run: it still completes.
    assert (await wait_terminal(registry, run.run_id)).status is RunStatus.COMPLETED


async def test_the_reaper_reports_worker_lost_runs():
    metrics = RecordingMetrics()
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    # A run whose owner died: registered, never driven, lease gone.
    await registry.try_acquire(make_run("r1"), lease_ttl_seconds=5)
    await log.append("r1", 1, "{}")
    registry.expire_lease("r1")
    reaper = OrphanRunReaper(registry=registry, event_log=log, settings=fast_settings(), metrics=metrics)

    assert await reaper.reap_once() == ["r1"]
    assert metrics.finished == [(RunStatus.INTERRUPTED, "worker_lost")]


async def test_end_reasons_are_bounded_for_metric_labels():
    assert bounded_reason(None) == "none"
    assert bounded_reason("worker_lost") == "worker_lost"
    assert bounded_reason("provider_rate_limited_4291") == "agent_error"
