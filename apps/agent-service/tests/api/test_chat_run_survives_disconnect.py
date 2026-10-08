"""Reproduces the bug: a client disconnect used to cancel the agent run itself."""

import asyncio
import json

import pytest

from app import app
from service.chat_runs.domain import ChatRunSpec
from tests.api.test_chat_route_activity import _patch_redis, _ThreadService, _UserService
from tests.gateway_auth import GATEWAY_HEADERS, allow_all_permissions, use_gateway_auth
from tests.service.chat_runs.fakes import use_in_memory_chat_runs, wait_terminal

SESSION = "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"


def _configure(monkeypatch, generator):
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    _patch_redis(monkeypatch)
    threads = _ThreadService()
    monkeypatch.setattr("api.routes.chat_route._get_thread_service", lambda: threads)
    monkeypatch.setattr("api.routes.chat_route.get_user_service", _UserService)
    monkeypatch.setattr("api.routes.chat_route.message_generator", generator)
    return threads, use_in_memory_chat_runs(monkeypatch)


async def _post_then_disconnect(body: dict, key: str, *, after_chunks: int = 1):
    """Drive the ASGI app directly so the client can vanish after ``after_chunks`` body chunks."""
    sent: list[dict] = []
    first_chunk = asyncio.Event()
    request_sent = False
    chunks = 0

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal chunks
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            chunks += 1
            if chunks >= after_chunks:
                first_chunk.set()

    headers = [(k.lower().encode(), v.encode()) for k, v in GATEWAY_HEADERS.items()]
    headers += [(b"content-type", b"application/json"), (b"idempotency-key", key.encode())]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/chat/messages",
        "raw_path": b"/api/v1/chat/messages",
        "query_string": b"",
        "headers": headers,
        "client": ("test", 1),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), 5)
    return sent


@pytest.mark.asyncio
async def test_the_run_finishes_after_the_client_disconnects(monkeypatch):
    finished = asyncio.Event()

    async def slow_agent(*_args):
        yield 'data: {"type": "token", "content": "first"}\n\n'
        await asyncio.sleep(0.2)  # the client is gone by now
        yield 'data: {"type": "token", "content": "second"}\n\n'
        finished.set()
        yield "data: [DONE]\n\n"

    _, runtime = _configure(monkeypatch, slow_agent)
    sent = await _post_then_disconnect({"message": "Hi", "chat_session_id": SESSION}, "disc-1")
    start = next(m for m in sent if m["type"] == "http.response.start")
    run_id = dict(start["headers"])[b"x-chat-run-id"].decode()

    await asyncio.wait_for(finished.wait(), 2)
    run = await wait_terminal(runtime.registry, run_id)
    assert run.status.value == "completed"
    payloads = [e.payload for e in await runtime.log.read_after(run_id, 0)]
    assert '{"type": "token", "content": "second"}' in payloads


TOKEN = '{"type": "token", "content": "after"}'
TOOL_START = '{"type": "custom_tool_start", "call_id": "c1"}'
TOOL_END = '{"type": "custom_tool_end", "call_id": "c1"}'
HUMAN_INPUT = '{"type": "human_input", "prompt": "Approve?"}'


def _agent(*steps):
    """An agent that pauses 0.2 s (the client is gone by then) before the last steps."""

    async def agent(*_args):
        for index, step in enumerate(steps):
            if index == 1:
                await asyncio.sleep(0.2)
            yield f"data: {step}\n\n"
        yield "data: [DONE]\n\n"

    return agent


# (agent steps, body chunks the client reads before vanishing, payloads the log must hold in order)
DISCONNECT_POINTS = {
    # run_started is the first chunk: the client leaves before any token exists.
    "before the first token": ((TOKEN,), 1, [TOKEN]),
    # run_started + the tool start: the client leaves while the tool is running.
    "mid tool call": ((TOOL_START, TOOL_END, TOKEN), 2, [TOOL_START, TOOL_END, TOKEN]),
    # run_started + the human_input packet: the run ends after its pause packet.
    "on a human input pause": ((HUMAN_INPUT,), 2, [HUMAN_INPUT]),
    # run_started + token + run_end: the client misses only [DONE].
    "just before [DONE]": ((TOKEN,), 3, [TOKEN]),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("point", list(DISCONNECT_POINTS))
async def test_the_run_completes_in_order_wherever_the_client_disconnects(monkeypatch, point):
    steps, after_chunks, expected = DISCONNECT_POINTS[point]
    _, runtime = _configure(monkeypatch, _agent(*steps))
    sent = await _post_then_disconnect(
        {"message": "Hi", "chat_session_id": SESSION}, f"disc-{list(DISCONNECT_POINTS).index(point)}", after_chunks=after_chunks
    )
    start = next(m for m in sent if m["type"] == "http.response.start")
    run_id = dict(start["headers"])[b"x-chat-run-id"].decode()

    run = await wait_terminal(runtime.registry, run_id)
    assert run.status.value == "completed"
    events = await runtime.log.read_after(run_id, 0)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))  # no gaps, no repeats
    payloads = [e.payload for e in events]
    assert '"run_started"' in payloads[0]
    assert '"run_end"' in payloads[-2] and payloads[-1] == "[DONE]"
    assert [p for p in payloads[1:-2]] == expected


def test_stream_frames_carry_ids_and_meta_packets(monkeypatch):
    from fastapi.testclient import TestClient

    async def agent(*_args):
        yield 'data: {"type": "token", "content": "hi"}\n\n'
        yield "data: [DONE]\n\n"

    _configure(monkeypatch, agent)
    response = TestClient(app, headers=GATEWAY_HEADERS).post(
        "/api/v1/chat/messages",
        headers={"Idempotency-Key": "ids-1"},
        json={"message": "Hi", "chat_session_id": SESSION},
    )
    frames = [f for f in response.text.split("\n\n") if f]
    assert frames[0].startswith("id: 1\ndata: ") and '"run_started"' in frames[0]
    assert '"run_end"' in frames[-2] and frames[-1].endswith("data: [DONE]")
    assert response.headers["x-chat-run-id"]


@pytest.mark.asyncio
async def test_second_send_on_a_busy_thread_is_rejected_before_side_effects(monkeypatch):
    import httpx

    release = asyncio.Event()

    async def long_agent(*_args):
        yield 'data: {"type": "token", "content": "busy"}\n\n'
        await release.wait()

    threads, runtime = _configure(monkeypatch, long_agent)
    active = await runtime.service.start(
        ChatRunSpec(thread_id=SESSION, owner_user_id="dev-user"), long_agent
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=GATEWAY_HEADERS
    ) as client:
        response = await client.post(
            "/api/v1/chat/messages",
            headers={"Idempotency-Key": "busy-2"},
            json={"message": "again", "chat_session_id": SESSION},
        )
    release.set()
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "chat_run.active"
    assert error["details"]["run_id"] == active.run_id
    assert error["message"] == "A response is still being generated in this chat."
    assert threads.activity_calls == []  # rejected before any thread mutation


@pytest.mark.asyncio
async def test_registry_outage_returns_503_without_a_dangling_lock(monkeypatch):
    import httpx

    async def agent(*_args):
        yield "data: [DONE]\n\n"

    _, runtime = _configure(monkeypatch, agent)

    async def broken(*_args, **_kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(runtime.registry, "try_acquire", broken)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=GATEWAY_HEADERS
    ) as client:
        response = await client.post(
            "/api/v1/chat/messages",
            headers={"Idempotency-Key": "down-1"},
            json={"message": "Hi", "chat_session_id": SESSION},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "chat_run.unavailable"
    assert response.json()["error"]["message"] == "The chat service is temporarily unavailable. Please try again."
    assert await runtime.registry.get_active_for_thread(SESSION) is None
