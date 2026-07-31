from collections.abc import AsyncIterator

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


class _UserController:
    async def resolve_projects_user_id(self, user_id: str) -> str:
        return user_id

    async def get_project_file_descriptors_for_chat(
        self,
        user_id: str | list[str],
        project_id: int | None,
        file_ids: list[str] | None = None,
    ) -> list[dict]:
        return [
            {
                "id": "project-note",
                "type": "document",
                "name": "project-note.txt",
                "user_file_id": "project-note",
                "data": "UHJvamVjdCBmaWxlIG1vZGVsIGNvbnRleHQu",
                "mime_type": "text/plain",
            }
        ]


class _ThreadControllerWithProjectColumn:
    async def get_thread(self, session_id: str) -> dict:
        return {
            "thread_id": session_id,
            "project_id": 5,
            "metadata": {
                "name": "Project chat",
                "persona_id": 0,
            },
        }

    async def create_thread(self, thread_id: str, metadata: dict) -> dict:
        raise AssertionError("existing project chat should not create a new thread")

    async def update_thread(self, session_id: str, metadata: dict) -> dict:
        return {
            "thread_id": session_id,
            "project_id": 5,
            "metadata": metadata,
        }


def test_send_chat_message_includes_project_files_in_agent_input(monkeypatch) -> None:
    captured: dict[str, StreamInput] = {}

    async def fake_message_generator(
        stream_input: StreamInput,
        assistant_id: str,
        user_id: str,
    ) -> AsyncIterator[str]:
        captured["stream_input"] = stream_input
        yield 'data: {"type": "done"}\n\n'

    async def fake_resolve_project_instructions(**kwargs) -> None:
        return None

    monkeypatch.setattr("api.routes.ChatRoute._get_thread_controller", _ThreadController)
    monkeypatch.setattr("api.routes.ChatRoute.get_user_controller", _UserController)
    monkeypatch.setattr("api.routes.ChatRoute.message_generator", fake_message_generator)
    monkeypatch.setattr(core_settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(AuthService.settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(core_settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(
        "api.routes.ChatRoute.resolve_project_instructions",
        fake_resolve_project_instructions,
    )

    response = TestClient(app).post(
        "/api/v1/chat/send-chat-message",
        json={
            "message": "Use the project file.",
            "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            "project_id": 5,
            "file_descriptors": [],
        },
    )

    assert response.status_code == 200
    stream_input = captured["stream_input"]
    assert stream_input.files_metadata == [
        {"id": "project-note", "type": "document", "name": "project-note.txt"}
    ]
    assert stream_input.file_content_blocks == [
        {
            "type": "text",
            "text": (
                "--- Begin Content of project-note.txt ---\n"
                "Project file model context.\n"
                "--- End Content of project-note.txt ---"
            ),
        }
    ]


def test_send_chat_message_resolves_project_files_from_thread_project_id(
    monkeypatch,
) -> None:
    captured: dict[str, StreamInput] = {}

    async def fake_message_generator(
        stream_input: StreamInput,
        assistant_id: str,
        user_id: str,
    ) -> AsyncIterator[str]:
        captured["stream_input"] = stream_input
        yield 'data: {"type": "done"}\n\n'

    async def fake_resolve_project_instructions(**kwargs) -> None:
        return None

    monkeypatch.setattr(
        "api.routes.ChatRoute._get_thread_controller",
        _ThreadControllerWithProjectColumn,
    )
    monkeypatch.setattr("api.routes.ChatRoute.get_user_controller", _UserController)
    monkeypatch.setattr("api.routes.ChatRoute.message_generator", fake_message_generator)
    monkeypatch.setattr(core_settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(AuthService.settings, "VALID_API_KEYS", "")
    monkeypatch.setattr(core_settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ENABLED", False)
    monkeypatch.setattr(
        "api.routes.ChatRoute.resolve_project_instructions",
        fake_resolve_project_instructions,
    )

    response = TestClient(app).post(
        "/api/v1/chat/send-chat-message",
        json={
            "message": "Use the project file.",
            "chat_session_id": "3a19f671-7d34-4cfd-9ea4-21e17491b3f5",
            "project_id": None,
            "file_descriptors": [],
        },
    )

    assert response.status_code == 200
    stream_input = captured["stream_input"]
    assert stream_input.files_metadata == [
        {"id": "project-note", "type": "document", "name": "project-note.txt"}
    ]
