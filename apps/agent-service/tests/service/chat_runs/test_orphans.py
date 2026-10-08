import json

import pytest

from service.chat_runs.domain import EventSequenceError, RunStatus
from service.chat_runs.frames import DONE_PAYLOAD
from service.chat_runs.orphans import close_event_log, finalize_orphan
from service.chat_runs.settings import ChatRunSettings
from tests.service.chat_runs.fakes import FakeClock, InMemoryRunEventLog, InMemoryRunRegistry
from tests.service.chat_runs.run_registry_contract import make_run

pytestmark = pytest.mark.asyncio


async def _payloads(log, run_id):
    return [e.payload for e in await log.read_after(run_id, 0)]


async def _running(registry, log, run_id="r1", thread_id="t1"):
    await registry.try_acquire(make_run(run_id, thread_id), lease_ttl_seconds=5)
    await log.append(run_id, 1, '{"type": "run_started"}')
    await log.append(run_id, 2, '{"type": "token", "content": "a"}')


async def test_finalizes_a_running_run_as_interrupted():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _running(registry, log)
    settings = ChatRunSettings(replay_ttl_seconds=900)
    assert await finalize_orphan(
        run_id="r1", registry=registry, event_log=log, settings=settings, clock=FakeClock()
    )
    run = await registry.get("r1")
    assert (run.status, run.error_code) == (RunStatus.INTERRUPTED, "worker_lost")
    payloads = await _payloads(log, "r1")
    assert json.loads(payloads[-2]) == {
        "type": "run_end",
        "status": "interrupted",
        "error_code": "worker_lost",
    }
    assert payloads[-1] == DONE_PAYLOAD
    assert await registry.get_active_for_thread("t1") is None
    assert log.expirations["r1"] == registry.expirations["r1"] == 900


async def test_a_second_finalize_is_a_noop():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _running(registry, log)
    kwargs = dict(
        registry=registry, event_log=log, settings=ChatRunSettings(), clock=FakeClock()
    )
    assert await finalize_orphan(run_id="r1", **kwargs)
    before = await _payloads(log, "r1")
    assert not await finalize_orphan(run_id="r1", **kwargs)
    assert await _payloads(log, "r1") == before


async def test_close_event_log_retries_when_a_racing_writer_takes_the_seq():
    log = InMemoryRunEventLog()
    await log.append("r1", 1, "x")

    class RacingLog:
        def __init__(self) -> None:
            self.raced = False

        async def last_seq(self, run_id):
            return await log.last_seq(run_id)

        async def append(self, run_id, seq, payload):
            if not self.raced:
                self.raced = True
                await log.append(run_id, seq, '{"type": "token", "content": "zombie"}')
                raise EventSequenceError(run_id, seq)
            await log.append(run_id, seq, payload)

    await close_event_log(RacingLog(), "r1", RunStatus.CANCELLED, None)
    payloads = await _payloads(log, "r1")
    assert [json.loads(p)["type"] for p in payloads if p.startswith("{")].count("run_end") == 1
    assert payloads[-1] == DONE_PAYLOAD


async def test_release_keeps_a_reclaimed_thread_lock():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await _running(registry, log, "old")
    registry.expire_lease("old")
    await registry.try_acquire(make_run("new"), lease_ttl_seconds=5)
    await finalize_orphan(
        run_id="old", registry=registry, event_log=log, settings=ChatRunSettings(), clock=FakeClock()
    )
    assert (await registry.get_active_for_thread("t1")).run_id == "new"


class _ExpireFailsLog(InMemoryRunEventLog):
    async def expire(self, run_id, ttl_seconds):
        raise ConnectionError("redis down")


async def test_the_thread_is_released_even_when_a_cleanup_step_fails():
    registry, log = InMemoryRunRegistry(), _ExpireFailsLog()
    await _running(registry, log)
    assert await finalize_orphan(
        run_id="r1", registry=registry, event_log=log, settings=ChatRunSettings(), clock=FakeClock()
    )
    assert await registry.get_active_for_thread("t1") is None
    assert (await registry.get("r1")).status is RunStatus.INTERRUPTED
