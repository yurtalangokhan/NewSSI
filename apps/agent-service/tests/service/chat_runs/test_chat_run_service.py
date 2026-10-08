import pytest

from service.chat_runs import provider
from service.chat_runs.domain import ChatRunSpec, ChatRunUnavailableError, RunAlreadyActiveError, RunNotFoundError
from tests.service.chat_runs.fakes import build_in_memory_chat_runs, frames_of, wait_terminal

pytestmark = pytest.mark.asyncio
SPEC = ChatRunSpec(thread_id="t1", owner_user_id="u1")


async def test_active_run_is_visible_only_to_its_owner():
    rt = build_in_memory_chat_runs()
    run = await rt.service.start(SPEC, frames_of("{}", delay=0.3))
    assert (await rt.service.get_active_run("t1", owner_ids={"u1"})).run_id == run.run_id
    assert await rt.service.get_active_run("t1", owner_ids={"intruder"}) is None
    await wait_terminal(rt.registry, run.run_id)


async def test_open_events_hides_unknown_and_foreign_runs():
    rt = build_in_memory_chat_runs()
    run = await rt.service.start(SPEC, frames_of("{}"))
    with pytest.raises(RunNotFoundError):
        await rt.service.open_events("nope", after_seq=0, owner_ids={"u1"})
    with pytest.raises(RunNotFoundError):
        await rt.service.open_events(run.run_id, after_seq=0, owner_ids={"intruder"})
    frames = [f async for f in await rt.service.open_events(run.run_id, after_seq=0, owner_ids={"u1"})]
    assert frames[-1].endswith("data: [DONE]\n\n")


async def test_cancel_active_cancels_the_threads_run():
    rt = build_in_memory_chat_runs()
    assert not await rt.service.cancel_active("t1")
    run = await rt.service.start(SPEC, frames_of("{}", delay=5))
    assert await rt.service.cancel_active("t1")
    assert (await wait_terminal(rt.registry, run.run_id)).status.value == "cancelled"


def test_provider_fails_loudly_when_unconfigured(monkeypatch):
    monkeypatch.setattr(provider, "_service", None)
    with pytest.raises(ChatRunUnavailableError):
        provider.get_chat_run_service()


async def test_ensure_idle_passes_on_an_idle_thread_and_rejects_a_busy_one():
    rt = build_in_memory_chat_runs()
    await rt.service.ensure_idle("t1", owner_ids={"u1"})
    run = await rt.service.start(SPEC, frames_of("{}", delay=0.3))
    with pytest.raises(RunAlreadyActiveError) as busy:
        await rt.service.ensure_idle("t1", owner_ids={"u1"})
    assert busy.value.run_id == run.run_id
    await wait_terminal(rt.registry, run.run_id)


async def test_ensure_idle_reports_a_failed_lookup_as_unavailable(monkeypatch):
    rt = build_in_memory_chat_runs()

    async def broken(_thread_id):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rt.registry, "get_active_for_thread", broken)
    with pytest.raises(ChatRunUnavailableError):
        await rt.service.ensure_idle("t1", owner_ids={"u1"})


async def test_start_and_subscribe_returns_the_run_and_its_replayable_stream():
    rt = build_in_memory_chat_runs()
    run, events = await rt.service.start_and_subscribe(SPEC, frames_of("{}"))
    frames = [frame async for frame in events]
    assert frames[0].startswith("id: 1\ndata: ") and "run_started" in frames[0]
    assert frames[-1].endswith("data: [DONE]\n\n")
    assert (await rt.registry.get(run.run_id)).status.value == "completed"


def _registry_down(monkeypatch, rt):
    async def broken(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rt.registry, "request_cancel_for_request", broken)
    monkeypatch.setattr(rt.registry, "get_active_for_thread", broken)
    monkeypatch.setattr(rt.registry, "request_cancel", broken)


async def test_stop_still_cancels_a_local_run_when_the_registry_is_down(monkeypatch):
    rt = build_in_memory_chat_runs()
    run = await rt.service.start(SPEC, frames_of("{}", delay=5))
    _registry_down(monkeypatch, rt)
    assert await rt.service.cancel_active("t1", client_request_id="k1") is True
    assert (await wait_terminal(rt.registry, run.run_id)).status.value == "cancelled"


async def test_stop_reports_unavailable_when_the_registry_is_down_and_no_run_is_local(monkeypatch):
    rt = build_in_memory_chat_runs()
    _registry_down(monkeypatch, rt)
    with pytest.raises(ChatRunUnavailableError):
        await rt.service.cancel_active("t1", client_request_id="k1")
