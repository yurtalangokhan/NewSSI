"""Every send-chat-message call must stamp which persona/agent it used onto
the outgoing agent_config, even for the default (model-chat) persona and
builtin personas that never go through resolve_custom_persona_agent. Retry
relies on this to report the correct agent per turn instead of the
thread-level metadata.persona_id, which only reflects the most recent send.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from idempotency import AsyncRedisPool

from app import app
from schemas.chat import StreamInput
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
    monkeypatch.setattr("infrastructure.db.repositories.persona_repo.PersonaRepository.get", staticmethod(fake_persona_get))
    monkeypatch.setattr(
        "api.routes.chat_route.resolve_project_instructions",
        fake_resolve_project_instructions,
    )


def _idempotency_headers(label: str) -> dict[str, str]:
    return {"Idempotency-Key": f"{label}-{uuid4()}"}


def test_send_chat_message_stamps_persona_id_for_default_and_builtin_personas(
    monkeypatch,
) -> None:
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)

    # A single TestClient/app lifecycle is reused for both requests — two
    # separate TestClient(app, headers=GATEWAY_HEADERS) instantiations in one test process leave a
    # stale async DB connection pool bound to the first one's event loop,
    # which crashes the second on unrelated teardown (a pre-existing test
    # infra issue orthogonal to persona_id resolution).
    from contextlib import nullcontext
    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        no_persona_response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("persona-stamping-default"),
            json={
                "message": "hello",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            },
        )
        assert no_persona_response.status_code == 200
        assert captured["stream_input"].agent_config.get("_persona_id") == 0
        assert captured["stream_input"].server_config == captured["stream_input"].agent_config

        builtin_persona_response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("persona-stamping-builtin"),
            json={
                "message": "hello",
                "chat_session_id": "9b6b8f2a-2e2f-4c4a-9a8b-1d2e3f4a5b6c",
                "persona_id": 1,
            },
        )
        assert builtin_persona_response.status_code == 200
        assert captured["stream_input"].agent_config.get("_persona_id") == 1


def test_send_chat_message_forwards_is_regenerate_flag(monkeypatch) -> None:
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)

    from contextlib import nullcontext
    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        normal_response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("regenerate-forward-normal"),
            json={
                "message": "hello",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            },
        )
        assert normal_response.status_code == 200
        assert captured["stream_input"].is_regenerate is False

        retry_response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("regenerate-forward-retry"),
            json={
                "message": "hello",
                "chat_session_id": "9b6b8f2a-2e2f-4c4a-9a8b-1d2e3f4a5b6c",
                "is_regenerate": True,
            },
        )
        assert retry_response.status_code == 200
        assert captured["stream_input"].is_regenerate is True


def test_builtin_persona_project_context_does_not_replace_the_agent_default_prompt(monkeypatch) -> None:
    """The project-context block is not a persona prompt: shipped as the run's
    server-side ``system_prompt`` it would replace the agent's default prompt
    (or hand a client-influenced system message to a plain chatbot)."""
    captured: dict[str, StreamInput] = {}
    _install_common_mocks(monkeypatch, captured)

    from contextlib import nullcontext
    with nullcontext(TestClient(app, headers=GATEWAY_HEADERS)) as client:
        response = client.post(
            "/api/v1/chat/messages",
            headers=_idempotency_headers("builtin-project-context"),
            json={
                "message": "hello",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
                "persona_id": 1,
                "additional_context": "client supplied context",
            },
        )

    assert response.status_code == 200
    assert "system_prompt" not in captured["stream_input"].server_config
