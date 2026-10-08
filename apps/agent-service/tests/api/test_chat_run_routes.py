import asyncio

import pytest
from fastapi.testclient import TestClient

from app import app
from service.chat_runs.domain import ChatRunSpec
from tests.api.test_chat_route_activity import _patch_redis
from tests.gateway_auth import GATEWAY_HEADERS, allow_all_permissions, use_gateway_auth
from tests.service.chat_runs.fakes import frames_of, use_in_memory_chat_runs

SESSION = "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"


class _Threads:
    def __init__(self, owner: str = "dev-user") -> None:
        self.owner = owner

    async def get_thread(self, thread_id):
        if thread_id != SESSION:
            return None
        return {"thread_id": thread_id, "metadata": {"user_id": self.owner}}

    async def update_thread(self, *args, **kwargs):
        return None


def _client(monkeypatch, owner="dev-user"):
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    _patch_redis(monkeypatch)
    monkeypatch.setattr("api.routes.chat_route._get_thread_service", lambda: _Threads(owner))
    runtime = use_in_memory_chat_runs(monkeypatch)
    return TestClient(app, headers=GATEWAY_HEADERS), runtime


def test_active_run_is_null_when_idle(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.get(f"/api/v1/chat/sessions/{SESSION}/active-run")
    assert response.status_code == 200
    assert response.json() == {"active_run": None}


def test_active_run_of_a_foreign_session_is_404(monkeypatch):
    client, _ = _client(monkeypatch, owner="someone-else")
    assert client.get(f"/api/v1/chat/sessions/{SESSION}/active-run").status_code == 404


@pytest.mark.asyncio
async def test_active_run_is_reported_while_running(monkeypatch):
    import httpx

    _, runtime = _client(monkeypatch)
    release = asyncio.Event()

    async def held():
        yield 'data: {"type": "token", "content": "x"}\n\n'
        await release.wait()

    run = await runtime.service.start(
        ChatRunSpec(thread_id=SESSION, owner_user_id="dev-user", client_request_id="k1"), held
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=GATEWAY_HEADERS
    ) as client:
        body = (await client.get(f"/api/v1/chat/sessions/{SESSION}/active-run")).json()
    release.set()
    assert body["active_run"]["run_id"] == run.run_id
    assert body["active_run"]["client_request_id"] == "k1"


@pytest.mark.asyncio
async def test_events_replay_a_finished_run_from_last_event_id(monkeypatch):
    import httpx

    from tests.service.chat_runs.fakes import wait_terminal

    _, runtime = _client(monkeypatch)
    run = await runtime.service.start(
        ChatRunSpec(thread_id=SESSION, owner_user_id="dev-user"),
        frames_of('{"type": "token", "content": "a"}', '{"type": "token", "content": "b"}'),
    )
    await wait_terminal(runtime.registry, run.run_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=GATEWAY_HEADERS
    ) as client:
        full = await client.get(f"/api/v1/chat/runs/{run.run_id}/events")
        resumed = await client.get(
            f"/api/v1/chat/runs/{run.run_id}/events?after=0", headers={"Last-Event-ID": "2"}
        )
        malformed = await client.get(
            f"/api/v1/chat/runs/{run.run_id}/events", headers={"Last-Event-ID": "x"}
        )
        unknown = await client.get("/api/v1/chat/runs/does-not-exist/events")
    assert full.text.startswith("id: 1\n")
    assert resumed.text.startswith("id: 3\n")
    assert resumed.text.rstrip().endswith("data: [DONE]")
    assert malformed.status_code == 422
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_events_of_someone_elses_run_are_404(monkeypatch):
    import httpx

    _, runtime = _client(monkeypatch)
    run = await runtime.service.start(
        ChatRunSpec(thread_id="other-thread", owner_user_id="someone-else"), frames_of("{}")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=GATEWAY_HEADERS
    ) as client:
        response = await client.get(f"/api/v1/chat/runs/{run.run_id}/events")
    assert response.status_code == 404


def test_stop_forwards_the_client_request_id(monkeypatch):
    client, runtime = _client(monkeypatch)
    response = client.post(
        f"/api/v1/chat/stop-chat-session/{SESSION}?client_request_id=k1", headers={"Idempotency-Key": "stop-1"}
    )
    assert response.status_code == 200

    async def check():
        return await runtime.registry.is_request_cancelled(SESSION, "k1")

    assert asyncio.run(check())


def test_stop_rejects_an_oversized_client_request_id(monkeypatch):
    client, _ = _client(monkeypatch)
    response = client.post(
        f"/api/v1/chat/stop-chat-session/{SESSION}?client_request_id={'x' * 300}", headers={"Idempotency-Key": "stop-2"}
    )
    assert response.status_code == 422
