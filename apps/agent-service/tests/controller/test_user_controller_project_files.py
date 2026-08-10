import base64

import pytest

from controller.user_controller import UserController


class _ProjectRepo:
    async def list_by_user_ids(self, user_ids: list[str]) -> list[dict]:
        return [
            {
                "id": 5,
                "user_id": "keycloak-subject",
                "name": "Legacy Project",
                "description": None,
                "instructions": None,
            }
            for user_id in user_ids
            if user_id == "keycloak-subject"
        ]

    async def get_for_user(self, user_id: str, project_id: int) -> dict:
        return {"id": project_id, "user_id": user_id, "name": "Test Project"}

    async def get_for_user_ids(self, user_ids: list[str], project_id: int) -> dict:
        return {"id": project_id, "user_id": user_ids[0], "name": "Test Project"}

    async def get_latest_user_id(self) -> str:
        return "latest-project-user"


class _Upload:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _DocumentRepo:
    async def create(self, **kwargs):
        return kwargs

    async def list_by_project(self, project_id: int) -> list[dict]:
        return []

    async def update_project_id(self, file_id: str, project_id: int) -> None:
        return None


@pytest.mark.asyncio
async def test_project_upload_is_available_as_chat_file_descriptor(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        _DocumentRepo,
    )
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()
    content = b"Project Hail Mary has important page-referenced notes."

    result = await controller.upload_user_project_files(
        user_id="keycloak-subject",
        files=[_Upload("hail-mary.txt", "text/plain", content)],
        project_id=5,
        temp_id_map_raw=None,
    )

    file_id = result["user_files"][0]["id"]
    descriptors = await controller.get_project_file_descriptors_for_chat(
        ["other-user", "keycloak-subject"], 5
    )

    assert len(descriptors) == 1
    assert descriptors[0]["id"] == file_id
    assert descriptors[0]["name"] == "hail-mary.txt"
    assert descriptors[0]["mime_type"] == "text/plain"
    assert base64.b64decode(descriptors[0]["data"]) == content


@pytest.mark.asyncio
async def test_user_file_can_be_linked_to_project_chat_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.db.repositories.document_repo.DocumentRepository",
        _DocumentRepo,
    )
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()
    content = b"Reusable user-library file content."

    result = await controller.upload_user_project_files(
        user_id="keycloak-subject",
        files=[_Upload("library-note.md", "text/markdown", content)],
        project_id=None,
        temp_id_map_raw=None,
    )
    file_id = result["user_files"][0]["id"]

    await controller.link_file_to_project(
        user_id="keycloak-subject",
        project_id=5,
        file_id=file_id,
    )

    descriptors = await controller.get_project_file_descriptors_for_chat("keycloak-subject", 5)

    assert len(descriptors) == 1
    assert descriptors[0]["id"] == file_id
    assert descriptors[0]["name"] == "library-note.md"
    assert descriptors[0]["mime_type"] == "text/markdown"
    assert base64.b64decode(descriptors[0]["data"]) == content


@pytest.mark.asyncio
async def test_project_user_id_keeps_keycloak_subject_for_existing_projects() -> None:
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()
    keycloak_subject = "8c92a872-38e0-4277-bb26-9599167f0131"

    assert await controller.resolve_projects_user_id(keycloak_subject) == keycloak_subject


@pytest.mark.asyncio
async def test_user_projects_use_owner_ids_without_leaking_other_threads(monkeypatch) -> None:
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()

    async def fake_list_chat_sessions_by_activity_from_store(*args, **kwargs):
        return [
            {
                "thread_id": "owned-thread",
                "metadata": {"user_id": "local-user", "project_id": 5, "name": "Owned"},
                "project_id": 5,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "thread_id": "other-thread",
                "metadata": {"user_id": "other-user", "project_id": 5, "name": "Other"},
                "project_id": 5,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        ]

    monkeypatch.setattr(
        "controller.user_controller.list_chat_sessions_by_activity_from_store",
        fake_list_chat_sessions_by_activity_from_store,
    )

    projects = await controller.get_user_projects(
        "local-user",
        owner_ids=["local-user", "keycloak-subject"],
    )

    assert len(projects) == 1
    assert projects[0]["id"] == 5
    assert [session["id"] for session in projects[0]["chat_sessions"]] == ["owned-thread"]
