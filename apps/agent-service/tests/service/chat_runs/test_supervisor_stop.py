import asyncio
import json

import pytest

from service.chat_runs.domain import ChatRunSpec, RunStatus, SupervisorShuttingDownError
from service.chat_runs.frames import DONE_PAYLOAD
from service.chat_runs.orphans import finalize_orphan
from service.chat_runs.supervisor import ChatRunSupervisor
from tests.service.chat_runs.fakes import (
    FakeClock,
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    fast_settings,
    frames_of,
    wait_terminal,
)

pytestmark = pytest.mark.asyncio
SPEC = ChatRunSpec(thread_id="t1", owner_user_id="u1")


def _run_ends(events):
    return [e for e in events if e.payload.startswith("{") and json.loads(e.payload)["type"] == "run_end"]


def _cooperative(flag: asyncio.Event):
    async def source():
        while not flag.is_set():
            yield 'data: {"type": "token", "content": "."}\n\n'
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return source


def _blocked_tool():
    async def source():
        yield 'data: {"type": "custom_tool_start", "call_id": "c1"}\n\n'
        try:
            await asyncio.sleep(30)  # a tool that ignores the cooperative flag
        finally:
            yield 'data: {"type": "flush"}\n\n'

    return source


class _SlowFinalizeRegistry(InMemoryRunRegistry):
    """Makes ``mark_terminal`` take real time, so a run can still be inside
    ``_finalize`` when ``shutdown()``'s grace period elapses -- the ordinary
    path that races ``shutdown()``'s own cancel against an in-flight finalize."""

    def __init__(self, delay: float) -> None:
        super().__init__()
        self._delay = delay

    async def mark_terminal(self, run_id, status, *, error_code, finished_at):
        await asyncio.sleep(self._delay)
        return await super().mark_terminal(run_id, status, error_code=error_code, finished_at=finished_at)


def _pair(**settings):
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    flag = asyncio.Event()

    def make(instance):
        return ChatRunSupervisor(
            registry=registry,
            event_log=log,
            settings=fast_settings(**settings),
            instance_id=instance,
            local_cancel=lambda _thread: flag.set(),
        )

    return make("a"), make("b"), registry, log, flag


async def test_local_cancel_stops_a_cooperative_run():
    a, _, registry, log, flag = _pair()
    run = await a.start(SPEC, _cooperative(flag))
    await asyncio.sleep(0.05)
    assert await a.cancel(run.run_id)
    finished = await wait_terminal(registry, run.run_id)
    assert finished.status is RunStatus.CANCELLED
    events = await log.read_after(run.run_id, 0)
    assert json.loads(_run_ends(events)[0].payload)["status"] == "cancelled"
    assert events[-1].payload == DONE_PAYLOAD


async def test_uncooperative_run_is_hard_cancelled_after_grace_and_its_finally_is_kept():
    a, _, registry, log, _ = _pair(cancel_grace_seconds=0.1)
    run = await a.start(SPEC, _blocked_tool())
    await asyncio.sleep(0.05)
    await a.cancel(run.run_id)
    finished = await wait_terminal(registry, run.run_id, timeout=1.0)
    assert finished.status is RunStatus.CANCELLED
    payloads = [e.payload for e in await log.read_after(run.run_id, 0)]
    assert '{"type": "flush"}' in payloads
    assert payloads.index('{"type": "flush"}') < payloads.index(DONE_PAYLOAD)


async def test_remote_cancel_hard_cancels_a_blocked_tool():
    a, b, registry, _, _ = _pair(cancel_grace_seconds=0.1)
    run = await a.start(SPEC, _blocked_tool())
    assert await b.cancel(run.run_id)  # b does not own the run
    finished = await wait_terminal(registry, run.run_id, timeout=1.0)
    assert finished.status is RunStatus.CANCELLED


async def test_cancel_after_completion_is_a_noop():
    a, _, registry, _, _ = _pair()
    run = await a.start(SPEC, frames_of('{"type": "token", "content": "x"}'))
    await wait_terminal(registry, run.run_id)
    assert not await a.cancel(run.run_id)
    assert not await registry.is_cancel_requested(run.run_id)


async def test_cancel_racing_completion_writes_one_run_end():
    a, _, registry, log, _ = _pair()
    run = await a.start(SPEC, frames_of('{"type": "token", "content": "x"}'))
    await asyncio.gather(a.cancel(run.run_id), wait_terminal(registry, run.run_id))
    await asyncio.sleep(0.05)
    assert len(_run_ends(await log.read_after(run.run_id, 0))) == 1


@pytest.mark.parametrize("cancel_after", [0.0, 0.015, 0.03, 0.045, 0.06, 0.09])
async def test_a_stop_racing_a_run_that_is_finishing_leaves_one_consistent_end(cancel_after):
    # A long lease keeps a slow machine from ending the run as lease_lost,
    # which is not the race under test.
    a, _, registry, log, _ = _pair(lease_ttl_seconds=30.0)

    async def finishing():
        for _ in range(6):
            await asyncio.sleep(0.015)
            yield 'data: {"type": "token", "content": "."}\n\n'

    run = await a.start(SPEC, finishing)
    await asyncio.sleep(cancel_after)  # sweeps the stop across the run's whole lifetime
    await a.cancel(run.run_id)
    finished = await wait_terminal(registry, run.run_id)
    await asyncio.sleep(0.05)
    ends = _run_ends(await log.read_after(run.run_id, 0))
    assert finished.status in (RunStatus.COMPLETED, RunStatus.CANCELLED)
    assert len(ends) == 1
    assert json.loads(ends[0].payload)["status"] == finished.status.value
    assert (await log.read_after(run.run_id, 0))[-1].payload == DONE_PAYLOAD


async def test_shutdown_waits_for_runs_that_finish_within_grace():
    a, _, registry, _, _ = _pair(shutdown_grace_seconds=1.0)
    run = await a.start(SPEC, frames_of('{"type": "token", "content": "x"}', delay=0.05))
    await a.shutdown()
    assert (await registry.get(run.run_id)).status is RunStatus.COMPLETED


async def test_shutdown_interrupts_runs_past_grace_and_rejects_new_starts():
    a, _, registry, log, _ = _pair(shutdown_grace_seconds=0.1)
    run = await a.start(SPEC, _blocked_tool())
    await a.shutdown()
    finished = await registry.get(run.run_id)
    assert (finished.status, finished.error_code) == (RunStatus.INTERRUPTED, "shutdown")
    assert (await log.read_after(run.run_id, 0))[-1].payload == DONE_PAYLOAD
    assert await registry.get_active_for_thread("t1") is None
    with pytest.raises(SupervisorShuttingDownError):
        await a.start(SPEC, frames_of("{}"))


async def test_lease_loss_stops_the_run():
    a, _, registry, _, _ = _pair()
    run = await a.start(SPEC, _blocked_tool())
    registry.expire_lease(run.run_id)
    finished = await wait_terminal(registry, run.run_id, timeout=1.0)
    assert (finished.status, finished.error_code) == (RunStatus.INTERRUPTED, "lease_lost")


async def test_reaped_run_keeps_the_reapers_single_run_end():
    a, _, registry, log, _ = _pair()
    run = await a.start(SPEC, _blocked_tool())
    registry.expire_lease(run.run_id)
    await finalize_orphan(
        run_id=run.run_id, registry=registry, event_log=log, settings=fast_settings(), clock=FakeClock()
    )
    await asyncio.sleep(0.3)  # owner notices the lost lease and stops
    ends = _run_ends(await log.read_after(run.run_id, 0))
    assert len(ends) == 1 and json.loads(ends[0].payload)["error_code"] == "worker_lost"
    assert run.run_id not in a.active_run_ids()


async def test_shutdown_waits_for_a_run_whose_finalize_is_still_in_flight():
    # A run that completes normally but whose _finalize (mark_terminal) is
    # still running when shutdown()'s grace period elapses. shutdown() then
    # cancels the drive task with zero further grace while it is still
    # suspended inside the shielded finalize -- shutdown() must not return
    # until that finalize has actually finished writing the terminal state
    # and releasing the thread lock.
    registry = _SlowFinalizeRegistry(delay=0.15)
    log = InMemoryRunEventLog()
    a = ChatRunSupervisor(
        registry=registry,
        event_log=log,
        settings=fast_settings(shutdown_grace_seconds=0.05, cancel_grace_seconds=0.05),
        instance_id="a",
    )
    run = await a.start(SPEC, frames_of('{"type": "token", "content": "x"}'))
    await a.shutdown()
    finished = await registry.get(run.run_id)
    assert finished is not None
    assert finished.status is not RunStatus.RUNNING
    assert await registry.get_active_for_thread("t1") is None


class _GatedAcquireRegistry(InMemoryRunRegistry):
    """Holds ``try_acquire`` open so a shutdown can begin while a start awaits it."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    async def try_acquire(self, run, **kwargs):
        self.entered.set()
        await self.gate.wait()
        return await super().try_acquire(run, **kwargs)


async def test_a_start_that_loses_the_race_with_shutdown_is_rolled_back():
    registry, log = _GatedAcquireRegistry(), InMemoryRunEventLog()
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=log, settings=fast_settings(shutdown_grace_seconds=0.1), instance_id="a"
    )
    starting = asyncio.create_task(supervisor.start(SPEC, _blocked_tool()))
    await registry.entered.wait()
    await supervisor.shutdown()  # takes its snapshot of live runs while the start is still acquiring
    registry.gate.set()
    with pytest.raises(SupervisorShuttingDownError):
        await starting
    assert supervisor.active_run_ids() == frozenset()
    assert await registry.get_active_for_thread("t1") is None  # the thread lock is released
    assert await registry.running_run_ids() == []
