import asyncio
import contextvars
import json

import pytest

from service.chat_runs.domain import (
    ChatRunSpec,
    ChatRunUnavailableError,
    RunAlreadyActiveError,
    RunStatus,
)
from service.chat_runs.frames import DONE_PAYLOAD
from service.chat_runs.supervisor import ChatRunSupervisor
from tests.service.chat_runs.fakes import (
    FailingEventLog,
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    fast_settings,
    frames_of,
    wait_terminal,
)
from tests.service.chat_runs.run_registry_contract import make_run

pytestmark = pytest.mark.asyncio
SPEC = ChatRunSpec(thread_id="t1", owner_user_id="u1", input_preview="hi")
TOKEN = '{"type": "token", "content": "a"}'


def _supervisor(**kwargs):
    registry = kwargs.pop("registry", InMemoryRunRegistry())
    log = kwargs.pop("event_log", InMemoryRunEventLog())
    settings = kwargs.pop("settings", fast_settings())
    sup = ChatRunSupervisor(
        registry=registry, event_log=log, settings=settings, instance_id="i1", **kwargs
    )
    return sup, registry, log


async def _events(log, run_id):
    return await log.read_after(run_id, 0)


async def test_run_completes_without_any_subscriber():
    sup, registry, log = _supervisor()
    run = await sup.start(SPEC, frames_of(TOKEN, "[DONE]"))
    finished = await wait_terminal(registry, run.run_id)
    events = await _events(log, run.run_id)
    assert finished.status is RunStatus.COMPLETED
    assert [e.seq for e in events] == [1, 2, 3, 4]
    assert json.loads(events[0].payload)["type"] == "run_started"
    assert events[1].payload == TOKEN
    assert json.loads(events[2].payload) == {
        "type": "run_end",
        "status": "completed",
        "error_code": None,
    }
    assert events[3].payload == DONE_PAYLOAD
    assert await registry.get_active_for_thread("t1") is None
    assert sup.active_run_ids() == frozenset()


async def test_generator_done_and_comment_frames_are_not_stored():
    sup, registry, log = _supervisor()
    run = await sup.start(SPEC, frames_of(": keep-alive\n\n", "[DONE]", TOKEN, "[DONE]"))
    await wait_terminal(registry, run.run_id)
    payloads = [e.payload for e in await _events(log, run.run_id)]
    assert payloads.count(DONE_PAYLOAD) == 1 and payloads[-1] == DONE_PAYLOAD
    assert TOKEN in payloads


async def test_error_payload_marks_the_run_failed():
    sup, registry, log = _supervisor()
    error = '{"type": "error", "error_code": "provider_unavailable"}'
    run = await sup.start(SPEC, frames_of(error, "[DONE]"))
    finished = await wait_terminal(registry, run.run_id)
    assert (finished.status, finished.error_code) == (RunStatus.FAILED, "provider_unavailable")


async def test_generator_exception_is_failed_and_still_closes_the_stream():
    async def boom():
        yield f"data: {TOKEN}\n\n"
        raise RuntimeError("bug")

    sup, registry, log = _supervisor()
    run = await sup.start(SPEC, lambda: boom())
    finished = await wait_terminal(registry, run.run_id)
    assert (finished.status, finished.error_code) == (RunStatus.FAILED, "internal_error")
    assert (await _events(log, run.run_id))[-1].payload == DONE_PAYLOAD
    assert await registry.get_active_for_thread("t1") is None


async def test_run_timeout_fails_the_run():
    async def forever():
        yield f"data: {TOKEN}\n\n"
        await asyncio.sleep(30)

    sup, registry, _ = _supervisor(settings=fast_settings(max_duration_seconds=1))
    run = await sup.start(SPEC, lambda: forever())
    finished = await wait_terminal(registry, run.run_id, timeout=3)
    assert (finished.status, finished.error_code) == (RunStatus.FAILED, "run_timeout")


async def test_busy_thread_is_rejected_with_the_holder():
    sup, registry, _ = _supervisor()
    first = await sup.start(SPEC, frames_of(TOKEN, delay=0.3))
    with pytest.raises(RunAlreadyActiveError) as exc:
        await sup.start(SPEC, frames_of(TOKEN))
    assert exc.value.run_id == first.run_id
    await wait_terminal(registry, first.run_id)


async def test_stale_lock_is_reclaimed_and_the_old_run_interrupted():
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    await registry.try_acquire(make_run("old", instance_id="dead"), lease_ttl_seconds=5)
    await log.append("old", 1, '{"type": "run_started"}')
    registry.expire_lease("old")
    sup, _, _ = _supervisor(registry=registry, event_log=log)
    run = await sup.start(SPEC, frames_of(TOKEN))
    old = await registry.get("old")
    assert (old.status, old.error_code) == (RunStatus.INTERRUPTED, "worker_lost")
    assert (await _events(log, "old"))[-1].payload == DONE_PAYLOAD
    await wait_terminal(registry, run.run_id)


async def test_start_failure_releases_the_thread():
    sup, registry, _ = _supervisor(event_log=FailingEventLog())
    with pytest.raises(ChatRunUnavailableError):
        await sup.start(SPEC, frames_of(TOKEN))
    assert await registry.get_active_for_thread("t1") is None
    [run_id] = [r for r in registry._runs]  # noqa: SLF001 - fake introspection
    assert (await registry.get(run_id)).error_code == "event_log_unavailable"


async def test_lease_is_renewed_while_running():
    sup, registry, _ = _supervisor()
    renewals = asyncio.Event()
    count = 0
    renew = registry.renew_lease

    async def counting(*args, **kwargs):
        nonlocal count
        count += 1
        if count >= 3:
            renewals.set()
        return await renew(*args, **kwargs)

    registry.renew_lease = counting  # type: ignore[method-assign]
    run = await sup.start(SPEC, frames_of(TOKEN, delay=0.6))
    # Waits for the renewals themselves, not for a wall-clock margin against
    # the lease, so a slow CI machine cannot turn this into a flake.
    await asyncio.wait_for(renewals.wait(), 3)
    assert await registry.has_live_lease(run.run_id)
    await wait_terminal(registry, run.run_id)


async def test_request_contextvars_flow_into_the_run():
    correlation = contextvars.ContextVar("correlation", default="none")

    async def echo():
        yield f'data: {{"type": "token", "content": "{correlation.get()}"}}\n\n'

    sup, registry, log = _supervisor()
    correlation.set("req-42")
    run = await sup.start(SPEC, lambda: echo())
    await wait_terminal(registry, run.run_id)
    assert "req-42" in (await _events(log, run.run_id))[1].payload


async def test_completion_hooks_run_for_completed_runs_and_are_isolated():
    seen: list[str] = []

    class Recording:
        async def on_run_completed(self, run):
            seen.append(run.run_id)

    class Exploding:
        async def on_run_completed(self, run):
            raise RuntimeError("hook bug")

    sup, registry, _ = _supervisor(hooks=[Exploding(), Recording()])
    ok = await sup.start(SPEC, frames_of(TOKEN))
    await wait_terminal(registry, ok.run_id)
    failed = await sup.start(
        ChatRunSpec(thread_id="t2", owner_user_id="u1"),
        frames_of('{"type": "error", "error_code": "x"}'),
    )
    await wait_terminal(registry, failed.run_id)
    await asyncio.sleep(0.05)
    assert seen == [ok.run_id]
