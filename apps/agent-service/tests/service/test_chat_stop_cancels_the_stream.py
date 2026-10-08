"""Stopping a chat session must actually cancel its in-flight stream.

stop_chat_session used to be a no-op: it acknowledged the request but
nothing during streaming ever checked for a stop signal, so the agent kept
running to completion regardless. This wires message_generator into
ActiveRunsService (already used by the separate SDK "runs" API) so a
concurrent stop_chat_session call breaks the stream loop.
"""

import asyncio
import json

import pytest

from schemas.chat import StreamInput
from service.runtime.active_runs_service import cancel_all_for_thread, is_cancelled
from tests.service.test_message_generator_flow_stage_events import (
    _FakeAssistantService,
    _FakeFlowAgent,
)


class _CancellableFlowAgent(_FakeFlowAgent):
    """Yields one stage, then waits for the test to call stop before
    the next one — a stand-in for a stop request landing mid-stream."""

    def __init__(self, first_stage_started: asyncio.Event) -> None:
        super().__init__()
        self._first_stage_started = first_stage_started

    async def astream(self, *args, **kwargs):
        yield ("debug", {"type": "task", "payload": {"id": "t1", "name": "ChatInput-1"}})
        self._first_stage_started.set()
        await asyncio.sleep(0.2)
        yield (
            "debug",
            {"type": "task", "payload": {"id": "t2", "name": "ShouldNotAppear-1"}},
        )
        yield (
            "debug",
            {
                "type": "task_result",
                "payload": {"id": "t2", "name": "ShouldNotAppear-1"},
            },
        )


async def _fake_handle_input_with_thread(_user_input, _agent, _user_id=None):
    return (
        {"input": {"messages": []}, "config": {"configurable": {"thread_id": "thread-cancel-1"}}},
        "run-cancel-1",
    )


@pytest.mark.asyncio
async def test_a_stop_request_breaks_the_stream_before_later_stages(monkeypatch):
    from service.orchestration import agent_stream_service as agents_route

    first_stage_started = asyncio.Event()
    monkeypatch.setattr(
        agents_route.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_CancellableFlowAgent(first_stage_started)),
    )
    monkeypatch.setattr(agents_route, "_handle_input", _fake_handle_input_with_thread)

    packets = []

    async def _consume():
        async for chunk in agents_route.message_generator(
            StreamInput(message="merhaba"), agent_id="flow-def-1", user_id="user-1"
        ):
            body = chunk.removeprefix("data: ").strip()
            if body and body != "[DONE]" and not chunk.startswith(":"):
                packets.append(json.loads(body))

    consumer = asyncio.create_task(_consume())
    await first_stage_started.wait()
    # Let the first stage's SSE packet actually reach `packets` before
    # cancelling — the event fires as soon as astream() resumes past its
    # first yield, which can race ahead of this task's own event-loop turn.
    await asyncio.sleep(0.05)
    cancel_all_for_thread("thread-cancel-1")
    await consumer

    starts = [p for p in packets if p["type"] == "graph_stage_start"]
    assert [p["stage_name"] for p in starts] == ["ChatInput-1"]
    assert not any(p.get("stage_name") == "ShouldNotAppear-1" for p in packets)


@pytest.mark.asyncio
async def test_the_run_is_unregistered_once_the_stream_ends(monkeypatch):
    from service.orchestration import agent_stream_service as agents_route

    monkeypatch.setattr(
        agents_route.AssistantAgentService,
        "get_instance",
        lambda: _FakeAssistantService(_FakeFlowAgent()),
    )
    monkeypatch.setattr(agents_route, "_handle_input", _fake_handle_input_with_thread)

    async for _chunk in agents_route.message_generator(
        StreamInput(message="merhaba"), agent_id="flow-def-1", user_id="user-1"
    ):
        pass

    # A finished run must not still answer to a stale cancel request.
    assert is_cancelled("thread-cancel-1", "run-cancel-1") is False


@pytest.mark.asyncio
async def test_stop_chat_session_signals_every_active_run_on_the_session():
    from service.chat.chat_management_service import ChatManagementService
    from service.runtime.active_runs_service import register_run

    class _OwnedThreads:
        """stop_chat_session now loads the thread to enforce ownership, so the
        fake must return a thread owned by user-1 (passing None would build a
        real thread service backed by a live DB pool bound to this test's event
        loop)."""

        async def get_thread(self, thread_id):
            return {"thread_id": thread_id, "metadata": {"user_id": "user-1"}}

        async def update_thread(self, *args, **kwargs):
            return None

    class _Runs:
        async def cancel_active(self, thread_id, *, client_request_id=None):
            return True

    service = ChatManagementService(
        thread_service=_OwnedThreads(), user_id="user-1", chat_runs=_Runs()
    )
    event = register_run("session-stop-1", "run-1")

    result = await service.stop_chat_session("session-stop-1")

    assert result == {"success": True}
    assert event.is_set()
