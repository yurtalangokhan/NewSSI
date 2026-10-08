"""Stop must end token generation, whenever it is pressed."""

import asyncio
import json

import pytest

from service.chat_runs.domain import ChatRunSpec, RunStatus
from service.chat_runs.supervisor import ChatRunSupervisor
from service.runtime.active_runs_service import bind_run_cancel_event, register_run, unregister_run
from tests.service.chat_runs.fakes import (
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    build_in_memory_chat_runs,
    fast_settings,
    wait_terminal,
)

pytestmark = pytest.mark.asyncio
TOKEN = 'data: {"type": "token", "content": "."}\n\n'


def _types(log: InMemoryRunEventLog, run_id: str) -> list[str]:
    return [
        json.loads(e.payload)["type"] if e.payload.startswith("{") else e.payload
        for e in log.events(run_id)
    ]


async def test_a_stop_before_the_run_is_registered_cancels_it_without_running_the_agent():
    # The Stop button is live while the POST is still being prepared: that
    # Stop finds no run, so the send it targets must not start one.
    rt = build_in_memory_chat_runs()
    started = asyncio.Event()

    async def agent():
        started.set()
        yield TOKEN

    assert not await rt.service.cancel_active("t1", client_request_id="k1")
    run = await rt.service.start(ChatRunSpec(thread_id="t1", owner_user_id="u1", client_request_id="k1"), agent)

    finished = await wait_terminal(rt.registry, run.run_id)
    assert finished.status is RunStatus.CANCELLED
    assert not started.is_set()
    assert _types(rt.log, run.run_id) == ["run_started", "run_end", "[DONE]"]


async def test_a_stop_for_an_earlier_send_does_not_cancel_the_next_one():
    rt = build_in_memory_chat_runs()

    async def agent():
        yield TOKEN

    await rt.service.cancel_active("t1", client_request_id="old")
    run = await rt.service.start(ChatRunSpec(thread_id="t1", owner_user_id="u1", client_request_id="new"), agent)

    assert (await wait_terminal(rt.registry, run.run_id)).status is RunStatus.COMPLETED


async def test_a_stop_reaches_a_generator_that_registers_its_cancel_event_late():
    # The agent registers its cooperative cancel event only after its own
    # setup; a Stop during that setup must still stop it before any token.
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    supervisor = ChatRunSupervisor(
        registry=registry,
        event_log=log,
        settings=fast_settings(cancel_grace_seconds=5.0),
        instance_id="i1",
        bind_cancel_event=bind_run_cancel_event,
    )
    setup_done = asyncio.Event()

    async def agent():
        await setup_done.wait()
        cancel = register_run("t1", "late")
        try:
            for _ in range(200):
                if cancel.is_set():
                    break
                yield TOKEN
                await asyncio.sleep(0.01)
        finally:
            unregister_run("t1", "late")

    run = await supervisor.start(ChatRunSpec(thread_id="t1", owner_user_id="u1"), agent)
    await asyncio.sleep(0.05)
    await supervisor.cancel(run.run_id)
    setup_done.set()

    # Cooperative (well inside the 5 s grace), and not a single token.
    finished = await asyncio.wait_for(wait_terminal(registry, run.run_id), 1.0)
    assert finished.status is RunStatus.CANCELLED
    assert "token" not in _types(log, run.run_id)


async def test_no_token_is_logged_once_the_stop_is_recorded():
    # A generator that ignores the cooperative flag keeps producing tokens
    # until the hard cancel; none of them may reach a viewer.
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog()
    supervisor = ChatRunSupervisor(
        registry=registry, event_log=log, settings=fast_settings(cancel_grace_seconds=0.3), instance_id="i1"
    )

    async def stubborn():
        while True:
            yield TOKEN
            await asyncio.sleep(0.01)

    run = await supervisor.start(ChatRunSpec(thread_id="t1", owner_user_id="u1"), stubborn)
    await asyncio.sleep(0.1)
    await supervisor.cancel(run.run_id)
    tokens_at_stop = _types(log, run.run_id).count("token")

    finished = await wait_terminal(registry, run.run_id)
    assert finished.status is RunStatus.CANCELLED
    assert _types(log, run.run_id).count("token") == tokens_at_stop
    assert _types(log, run.run_id)[-2:] == ["run_end", "[DONE]"]
