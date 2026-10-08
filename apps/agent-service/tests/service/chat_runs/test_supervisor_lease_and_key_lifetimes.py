"""Stop, lease loss and key lifetimes: regressions found in the pre-release review."""

import asyncio

import pytest

from service.chat_runs.domain import ChatRunSpec, RunStatus
from service.chat_runs.supervisor import ChatRunSupervisor
from tests.service.chat_runs.fakes import (
    FailingEventLog,
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    fast_settings,
    wait_terminal,
)

pytestmark = pytest.mark.asyncio
SPEC = ChatRunSpec(thread_id="t1", owner_user_id="u1")


def _slow_to_stop(stopping: asyncio.Event, finally_seconds: float):
    """A run whose cooperative stop takes longer than the lease TTL (a slow
    timeline write in the generator's finally)."""

    async def source():
        yield 'data: {"type": "token", "content": "."}\n\n'
        await stopping.wait()
        await asyncio.sleep(finally_seconds)
        yield "data: [DONE]\n\n"

    return source


async def test_a_stopped_run_keeps_its_lease_until_it_is_finalized():
    registry = InMemoryRunRegistry()
    settings = fast_settings(lease_ttl_seconds=0.3, cancel_grace_seconds=2.0)
    stopping = asyncio.Event()
    supervisor = ChatRunSupervisor(
        registry=registry,
        event_log=InMemoryRunEventLog(),
        settings=settings,
        instance_id="i1",
        local_cancel=lambda _thread_id: stopping.set(),
    )
    run = await supervisor.start(SPEC, _slow_to_stop(stopping, finally_seconds=0.8))
    await registry.request_cancel(run.run_id, ttl_seconds=600)

    # The cooperative stop outlives the lease TTL; renewal must continue.
    await asyncio.sleep(0.6)
    assert await registry.has_live_lease(run.run_id)

    finished = await wait_terminal(registry, run.run_id)
    assert finished.status is RunStatus.CANCELLED


async def test_lease_loss_never_cooperatively_cancels_the_thread():
    # The thread-scoped cooperative cancel would also hit a newer run that
    # reclaimed the thread on this instance.
    registry = InMemoryRunRegistry()
    cancelled_threads: list[str] = []
    supervisor = ChatRunSupervisor(
        registry=registry,
        event_log=InMemoryRunEventLog(),
        settings=fast_settings(),
        instance_id="i1",
        local_cancel=cancelled_threads.append,
    )

    async def endless():
        while True:
            yield 'data: {"type": "token", "content": "."}\n\n'
            await asyncio.sleep(0.02)

    run = await supervisor.start(SPEC, endless)
    registry.expire_lease(run.run_id)

    finished = await wait_terminal(registry, run.run_id)
    assert finished.status is RunStatus.INTERRUPTED
    assert cancelled_threads == []


async def test_a_failed_start_still_expires_the_run_hash():
    registry = InMemoryRunRegistry()
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=FailingEventLog(), settings=fast_settings(), instance_id="i1"
    )
    with pytest.raises(Exception):
        await supervisor.start(SPEC, lambda: None)
    (run_id,) = registry.expirations
    assert registry.expirations[run_id] <= fast_settings().replay_ttl_seconds


async def test_start_bounds_the_run_hash_lifetime():
    registry = InMemoryRunRegistry()
    settings = fast_settings()
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=InMemoryRunEventLog(), settings=settings, instance_id="i1"
    )

    async def one():
        yield "data: [DONE]\n\n"

    run = await supervisor.start(SPEC, one)
    assert registry.acquire_ttls[run.run_id] == settings.max_duration_seconds + settings.replay_ttl_seconds
    await wait_terminal(registry, run.run_id)
