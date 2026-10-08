"""Task 16a fix round 1: the reviewer found `document_context` was parsed by
neither `parse_chat_request` nor forwarded into `StreamInput`, so a
client-sent open document never reached the coordinator's
`configurable["active_document"]` on the actual product chat path
(`send_chat_message` / POST /api/chat/messages). These tests exercise the
whole route, mirroring the pattern in
`test_chat_route_persona_id_stamping.py`.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from idempotency import AsyncRedisPool

from app import app
from schemas.chat import DocumentContext, StreamInput
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


def _patch_redis(monkeypatch) -> None:
    redis = _FakeRedis()

    async def connect(config) -> _FakeRedis:
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)


class _ThreadService:
    async def get_thread(self, session_id: str) -> dict | None:
        return None

    async def create_thread(self, thread_id: str, metadata: dict) -> dict:
        return {
            "thread_id": thread_id,
            "metadata": metadata,
        }


class _UserService:
    async def resolve_projects_user_id(self, user_id: str) -> str:
        return user_id


def _install_common_mocks(monkeypatch, captured: dict) -> None:
    use_gateway_auth(monkeypatch)
    allow_all_permissions(monkeypatch)
    _patch_redis(monkeypatch)
    use_in_memory_chat_runs(monkeypatch)
    monkeypatch.setattr("api.routes.chat_route.get_user_service", _UserService)

    async def fake_message_generator(
        stream_input: StreamInput,
        assistant_id: str,
        user_id: str,
    ) -> AsyncIterator[str]:
        captured["stream_input"] = stream_input
        yield 'data: {"type": "done"}\n\n'

    async def fake_resolve_project_instructions(**kwargs) -> None:
        return None

    async def fake_persona_get(persona_id: int) -> None:
        return None

    monkeypatch.setattr("api.routes.chat_route._get_thread_service", _ThreadService)
    monkeypatch.setattr("api.routes.chat_route.message_generator", fake_message_generator)
    monkeypatch.setattr(
        "infrastructure.db.repositories.persona_repo.PersonaRepository.get",
        staticmethod(fake_persona_get),
    )
    monkeypatch.setattr(
        "api.routes.chat_route.resolve_project_instructions",
        fake_resolve_project_instructions,
    )


def _idempotency_headers(label: str) -> dict[str, str]:
    return {"Idempotency-Key": f"{label}-{uuid4()}"}


def test_send_chat_message_forwards_document_context_to_stream_input(monkeypatch) -> None:
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)
    document_id = uuid4()

    from contextlib import nullcontext

    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("document-context-forward"),
            json={
                "message": "x",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
                "document_context": {"document_id": str(document_id), "revision_no": 2},
            },
        )

        assert response.status_code == 200
        stream_input = captured["stream_input"]
        assert stream_input.document_context == DocumentContext(
            document_id=document_id, revision_no=2
        )
        # The message itself must stay untouched -- no note injected.
        assert stream_input.message == "x"


def test_send_chat_message_omits_document_context_when_not_sent(monkeypatch) -> None:
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)

    from contextlib import nullcontext

    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("document-context-absent"),
            json={
                "message": "hello",
                "chat_session_id": "9b6b8f2a-2e2f-4c4a-9a8b-1d2e3f4a5b6c",
            },
        )

        assert response.status_code == 200
        assert captured["stream_input"].document_context is None


def test_send_chat_message_rejects_malformed_document_context(monkeypatch) -> None:
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)

    from contextlib import nullcontext

    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("document-context-malformed"),
            json={
                "message": "hello",
                "chat_session_id": "489e5f0d-6f3d-4a4b-9f0d-2f0e3d4c5b6a",
                "document_context": {"document_id": "not-a-uuid"},
            },
        )

        assert response.status_code == 422
        assert "stream_input" not in captured
