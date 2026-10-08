"""Route coverage for accepted user-message activity marking."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient
from idempotency import AsyncRedisPool

from app import app
from tests.gateway_auth import GATEWAY_HEADERS, use_gateway_auth, allow_all_permissions
from tests.service.chat_runs.fakes import use_in_memory_chat_runs


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        key = keys_and_args[0]
        token = keys_and_args[1]
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        return sum(self.values.pop(key, None) is not None for key in keys)



class _ThreadService:
    def __init__(self) -> None:
        self.activity_calls: list[str] = []
        self.events: list[str] = []

    async def get_thread(self, session_id: str) -> dict:
        return {
            "thread_id": session_id,
            "metadata": {"user_id": "dev-user", "name": "Existing chat", "persona_id": 0},
        }

    async def create_thread(self, thread_id: str, metadata: dict) -> dict:
        return {"thread_id": thread_id, "metadata": metadata}

    async def mark_message_activity(self, session_id: str) -> dict:
        self.activity_calls.append(session_id)
        self.events.append("activity-marked")
        return {"thread_id": session_id}


class _UserService:
    async def resolve_projects_user_id(self, user_id: str) -> str:
        return user_id



def _patch_redis(monkeypatch) -> None:
    redis = _FakeRedis()

    async def connect(config) -> _FakeRedis:
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)


def _configure_route(monkeypatch, thread_controller: _ThreadService, message_generator) -> None:
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    _patch_redis(monkeypatch)
    monkeypatch.setattr("api.routes.chat_route._get_thread_service", lambda: thread_controller)
    monkeypatch.setattr("api.routes.chat_route.get_user_service", _UserService)
    monkeypatch.setattr("api.routes.chat_route.message_generator", message_generator)
    use_in_memory_chat_runs(monkeypatch)


def test_send_message_marks_activity_before_provider_failure(monkeypatch) -> None:
    thread_service = _ThreadService()

    async def failing_generator(*_args) -> AsyncIterator[str]:
        raise RuntimeError("provider unavailable")
        yield ""

    _configure_route(monkeypatch, thread_service, failing_generator)

    response = TestClient(app, headers=GATEWAY_HEADERS).post(
        "/api/v1/chat/messages",
        headers={"Idempotency-Key": "activity-provider-failure"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_service.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]


def test_send_message_keeps_activity_after_partial_stream(monkeypatch) -> None:
    thread_service = _ThreadService()

    async def partial_generator(*_args) -> AsyncIterator[str]:
        thread_service.events.append("stream-started")
        yield 'data: {"type": "token", "content": "partial"}\n\n'
        raise RuntimeError("stream interrupted")

    _configure_route(monkeypatch, thread_service, partial_generator)

    response = TestClient(app, headers=GATEWAY_HEADERS).post(
        "/api/v1/chat/messages",
        headers={"Idempotency-Key": "activity-partial-stream"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_service.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]
    assert thread_service.events == ["activity-marked", "stream-started"]


def test_send_message_marks_activity_before_client_cancellation(monkeypatch) -> None:
    thread_service = _ThreadService()

    async def cancelling_generator(*_args) -> AsyncIterator[str]:
        thread_service.events.append("stream-started")
        raise asyncio.CancelledError()
        yield ""

    _configure_route(monkeypatch, thread_service, cancelling_generator)

    response = TestClient(app, headers=GATEWAY_HEADERS).post(
        "/api/v1/chat/messages",
        headers={"Idempotency-Key": "activity-client-cancellation"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_service.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]
    assert thread_service.events == ["activity-marked", "stream-started"]


def test_chat_session_list_forwards_activity_cursor(monkeypatch) -> None:
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    class _ChatService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def get_chat_sessions(self, **kwargs) -> dict:
            self.calls.append(kwargs)
            return {"sessions": [], "chat_sessions": [], "has_more": False, "next_cursor": None}

    service = _ChatService()

    async def fake_get_user_chat_service(*_args) -> _ChatService:
        return service

    monkeypatch.setattr(
        "api.routes.chat_route._get_user_chat_service", fake_get_user_chat_service
    )

    response = TestClient(app, headers=GATEWAY_HEADERS).get(
        "/api/v1/chat/sessions?page_size=2&before_activity=2026-08-07T10%3A00%3A00%2B00%3A00&before_id=thread-2"
    )

    assert response.status_code == 200
    assert service.calls == [
        {
            "page_size": 2,
            "before_activity": "2026-08-07T10:00:00+00:00",
            "before_id": "thread-2",
            "query": None,
            "agents_only": False,
        }
    ]


def test_chat_session_list_forwards_search_and_agent_filter(monkeypatch) -> None:
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    calls: list[dict] = []

    class _ChatService:
        async def get_chat_sessions(self, **kwargs) -> dict:
            calls.append(kwargs)
            return {"sessions": [], "chat_sessions": [], "has_more": False, "next_cursor": None}

    async def fake_get_user_chat_service(*_args) -> _ChatService:
        return _ChatService()

    monkeypatch.setattr(
        "api.routes.chat_route._get_user_chat_service", fake_get_user_chat_service
    )

    response = TestClient(app, headers=GATEWAY_HEADERS).get(
        "/api/v1/chat/sessions?q=report&agents_only=true"
    )

    assert response.status_code == 200
    assert calls[0]["query"] == "report"
    assert calls[0]["agents_only"] is True


def test_chat_session_list_rejects_search_longer_than_200_characters(monkeypatch) -> None:
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)

    response = TestClient(app, headers=GATEWAY_HEADERS).get(
        f"/api/v1/chat/sessions?q={'a' * 201}"
    )

    assert response.status_code == 422
