"""Route coverage for accepted user-message activity marking."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient
from idempotency import AsyncRedisPool

from app import app
from core import settings as core_settings
from service import AuthService


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


class _ThreadController:
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


class _UserController:
    async def resolve_projects_user_id(self, user_id: str) -> str:
        return user_id


def _patch_redis(monkeypatch) -> None:
    redis = _FakeRedis()

    async def connect(config) -> _FakeRedis:
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)


def _configure_route(monkeypatch, thread_controller: _ThreadController, message_generator) -> None:
    _patch_redis(monkeypatch)
    monkeypatch.setattr("api.routes.ChatRoute._get_thread_controller", lambda: thread_controller)
    monkeypatch.setattr("api.routes.ChatRoute.get_user_controller", _UserController)
    monkeypatch.setattr("api.routes.ChatRoute.message_generator", message_generator)
    monkeypatch.setattr(core_settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(AuthService.settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(core_settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ENABLED", False)


def test_send_message_marks_activity_before_provider_failure(monkeypatch) -> None:
    thread_controller = _ThreadController()

    async def failing_generator(*_args) -> AsyncIterator[str]:
        raise RuntimeError("provider unavailable")
        yield ""

    _configure_route(monkeypatch, thread_controller, failing_generator)

    response = TestClient(app).post(
        "/api/v1/chat/send-chat-message",
        headers={"Idempotency-Key": "activity-provider-failure"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_controller.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]


def test_send_message_keeps_activity_after_partial_stream(monkeypatch) -> None:
    thread_controller = _ThreadController()

    async def partial_generator(*_args) -> AsyncIterator[str]:
        thread_controller.events.append("stream-started")
        yield 'data: {"type": "token", "content": "partial"}\n\n'
        raise RuntimeError("stream interrupted")

    _configure_route(monkeypatch, thread_controller, partial_generator)

    response = TestClient(app).post(
        "/api/v1/chat/send-chat-message",
        headers={"Idempotency-Key": "activity-partial-stream"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_controller.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]
    assert thread_controller.events == ["activity-marked", "stream-started"]


def test_send_message_marks_activity_before_client_cancellation(monkeypatch) -> None:
    thread_controller = _ThreadController()

    async def cancelling_generator(*_args) -> AsyncIterator[str]:
        thread_controller.events.append("stream-started")
        raise asyncio.CancelledError()
        yield ""

    _configure_route(monkeypatch, thread_controller, cancelling_generator)

    response = TestClient(app).post(
        "/api/v1/chat/send-chat-message",
        headers={"Idempotency-Key": "activity-client-cancellation"},
        json={"message": "Hello", "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5"},
    )

    assert response.status_code == 200
    assert thread_controller.activity_calls == ["3a19f671-7d34-4cfd-9ea4-21e17491b3f5"]
    assert thread_controller.events == ["activity-marked", "stream-started"]


def test_chat_session_list_forwards_activity_cursor(monkeypatch) -> None:
    class _ChatController:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def get_chat_sessions(self, **kwargs) -> dict:
            self.calls.append(kwargs)
            return {"sessions": [], "chat_sessions": [], "has_more": False, "next_cursor": None}

    controller = _ChatController()

    async def fake_get_user_chat_controller(*_args) -> _ChatController:
        return controller

    monkeypatch.setattr(
        "api.routes.ChatRoute._get_user_chat_controller", fake_get_user_chat_controller
    )
    monkeypatch.setattr(core_settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(AuthService.settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(core_settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ENABLED", False)

    response = TestClient(app).get(
        "/api/v1/chat/sessions?page_size=2&before_activity=2026-08-07T10%3A00%3A00%2B00%3A00&before_id=thread-2"
    )

    assert response.status_code == 200
    assert controller.calls == [
        {
            "page_size": 2,
            "before_activity": "2026-08-07T10:00:00+00:00",
            "before_id": "thread-2",
        }
    ]
