"""Every send-chat-message call must stamp which persona/agent it used onto
the outgoing agent_config, even for the default (model-chat) persona and
builtin personas that never go through _resolve_custom_persona_agent. Retry
relies on this to report the correct agent per turn instead of the
thread-level metadata.persona_id, which only reflects the most recent send.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi.testclient import TestClient

from app import app
from core import settings as core_settings
from models.chat import StreamInput
from service import AuthService


class _ThreadController:
    async def get_thread(self, session_id: str) -> dict | None:
        return None

    async def create_thread(self, thread_id: str, metadata: dict) -> dict:
        return {
            "thread_id": thread_id,
            "metadata": metadata,
        }


def _install_common_mocks(monkeypatch, captured: dict) -> None:
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

    monkeypatch.setattr("api.routes.ChatRoute._get_thread_controller", _ThreadController)
    monkeypatch.setattr("api.routes.ChatRoute.message_generator", fake_message_generator)
    monkeypatch.setattr("repository.persona_repository.PersonaDB.get", fake_persona_get)
    monkeypatch.setattr(core_settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(AuthService.settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(core_settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(
        "api.routes.ChatRoute.resolve_project_instructions",
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
    # separate TestClient(app) instantiations in one test process leave a
    # stale async DB connection pool bound to the first one's event loop,
    # which crashes the second on unrelated teardown (a pre-existing test
    # infra issue orthogonal to persona_id resolution).
    with TestClient(app) as client:
        no_persona_response = client.post(
            "/api/v1/chat/send-chat-message",
            headers=_idempotency_headers("persona-stamping-default"),
            json={
                "message": "hello",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            },
        )
        assert no_persona_response.status_code == 200
        assert captured["stream_input"].agent_config.get("_persona_id") == 0

        builtin_persona_response = client.post(
            "/api/v1/chat/send-chat-message",
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

    with TestClient(app) as client:
        normal_response = client.post(
            "/api/v1/chat/send-chat-message",
            headers=_idempotency_headers("regenerate-forward-normal"),
            json={
                "message": "hello",
                "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            },
        )
        assert normal_response.status_code == 200
        assert captured["stream_input"].is_regenerate is False

        retry_response = client.post(
            "/api/v1/chat/send-chat-message",
            headers=_idempotency_headers("regenerate-forward-retry"),
            json={
                "message": "hello",
                "chat_session_id": "9b6b8f2a-2e2f-4c4a-9a8b-1d2e3f4a5b6c",
                "is_regenerate": True,
            },
        )
        assert retry_response.status_code == 200
        assert captured["stream_input"].is_regenerate is True
