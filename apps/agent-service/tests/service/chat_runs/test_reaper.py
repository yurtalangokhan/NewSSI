import asyncio
import json

import pytest

from service.chat_runs.domain import EventSequenceError, RunStatus
from service.chat_runs.reaper import OrphanRunReaper
from tests.service.chat_runs.fakes import InMemoryRunEventLog, InMemoryRunRegistry, fast_settings
from tests.service.chat_runs.run_registry_contract import make_run

pytestmark = pytest.mark.asyncio


async def _orphan(registry, log, run_id="r1", thread_id="t1"):
    await registry.try_acquire(make_run(run_id, thread_id), lease_ttl_seconds=30)
    await log.append(run_id, 1, '{"type": "run_started"}')
    registry.expire_lease(run_id)


def _reaper(registry, log):
    return OrphanRunReaper(registry=registry, event_log=log, settings=fast_settings())


async def test_reaps_a_run_whose_lease_expired():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _orphan(registry, log)
    assert await _reaper(registry, log).reap_once() == ["r1"]
    run = await registry.get("r1")
    assert (run.status, run.error_code) == (RunStatus.INTERRUPTED, "worker_lost")
    assert await registry.get_active_for_thread("t1") is None


async def test_leaves_live_runs_alone():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await registry.try_acquire(make_run("r1"), lease_ttl_seconds=30)
    assert await _reaper(registry, log).reap_once() == []
    assert (await registry.get("r1")).status is RunStatus.RUNNING


async def test_concurrent_reapers_write_one_run_end():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _orphan(registry, log)
    results = await asyncio.gather(
        _reaper(registry, log).reap_once(), _reaper(registry, log).reap_once()
    )
    assert sorted(len(r) for r in results) == [0, 1]
    ends = [
        e for e in await log.read_after("r1", 0)
        if e.payload.startswith("{") and json.loads(e.payload)["type"] == "run_end"
    ]
    assert len(ends) == 1


async def test_a_zombie_writer_is_fenced_after_reaping():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _orphan(registry, log)
    await _reaper(registry, log).reap_once()
    with pytest.raises(EventSequenceError):
        await log.append("r1", 2, '{"type": "token", "content": "late"}')


async def test_loop_reaps_periodically_and_survives_errors():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    calls = {"n": 0}
    original = registry.running_run_ids

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("redis blip")
        return await original()

    registry.running_run_ids = flaky
    await _orphan(registry, log)
    reaper = _reaper(registry, log)
    reaper.start()
    try:
        for _ in range(40):
            if (await registry.get("r1")).status.is_terminal:
                break
            await asyncio.sleep(0.02)
    finally:
        await reaper.stop()
    assert (await registry.get("r1")).status is RunStatus.INTERRUPTED
