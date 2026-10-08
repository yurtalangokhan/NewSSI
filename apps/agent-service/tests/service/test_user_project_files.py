import base64

import pytest

from service.users.user_service import UserService


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
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        _DocumentRepo,
    )
    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()
    content = b"Project Hail Mary has important page-referenced notes."

    result = await service.upload_user_project_files(
        user_id="keycloak-subject",
        files=[_Upload("hail-mary.txt", "text/plain", content)],
        project_id=5,
        temp_id_map_raw=None,
    )

    file_id = result["user_files"][0]["id"]
    descriptors = await service.get_project_file_descriptors_for_chat(
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
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        _DocumentRepo,
    )
    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()
    content = b"Reusable user-library file content."

    result = await service.upload_user_project_files(
        user_id="keycloak-subject",
        files=[_Upload("library-note.md", "text/markdown", content)],
        project_id=None,
        temp_id_map_raw=None,
    )
    file_id = result["user_files"][0]["id"]

    await service.link_file_to_project(
        user_id="keycloak-subject",
        project_id=5,
        file_id=file_id,
    )

    descriptors = await service.get_project_file_descriptors_for_chat("keycloak-subject", 5)

    assert len(descriptors) == 1
    assert descriptors[0]["id"] == file_id
    assert descriptors[0]["name"] == "library-note.md"
    assert descriptors[0]["mime_type"] == "text/markdown"
    assert base64.b64decode(descriptors[0]["data"]) == content


@pytest.mark.asyncio
async def test_upload_does_not_keep_a_second_base64_copy_of_the_bytes(monkeypatch) -> None:
    """FileService.store_file already holds these exact bytes.

    Immediately re-encoding and caching them again in
    UserService._file_payloads_by_user was a second full copy of every
    upload, made at upload time whether or not a chat turn ever asked for
    it. Chat context can read the bytes FileService already has instead of
    keeping its own.
    """
    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository",
        _DocumentRepo,
    )
    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()
    content = b"No second copy of this, please."

    result = await service.upload_user_project_files(
        user_id="keycloak-subject",
        files=[_Upload("once.txt", "text/plain", content)],
        project_id=5,
        temp_id_map_raw=None,
    )
    file_id = result["user_files"][0]["id"]

    assert file_id not in service._file_payloads("keycloak-subject"), (
        "upload pre-emptively cached a base64 copy FileService already stores"
    )

    descriptors = await service.get_project_file_descriptors_for_chat(["keycloak-subject"], 5)

    assert len(descriptors) == 1
    assert base64.b64decode(descriptors[0]["data"]) == content


@pytest.mark.asyncio
async def test_project_user_id_keeps_keycloak_subject_for_existing_projects() -> None:
    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()
    keycloak_subject = "8c92a872-38e0-4277-bb26-9599167f0131"

    assert await service.resolve_projects_user_id(keycloak_subject) == keycloak_subject


@pytest.mark.asyncio
async def test_user_projects_use_owner_ids_without_leaking_other_threads(monkeypatch) -> None:
    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()

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
        "service.users.user_service.list_chat_sessions_by_activity_from_store",
        fake_list_chat_sessions_by_activity_from_store,
    )

    projects = await service.get_user_projects(
        "local-user",
        owner_ids=["local-user", "keycloak-subject"],
    )

    assert len(projects) == 1
    assert projects[0]["id"] == 5
    assert [session["id"] for session in projects[0]["chat_sessions"]] == ["owned-thread"]


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "tr"])
async def test_rejected_project_upload_uses_request_locale(locale):
    from localization.core import reset_locale, set_locale

    service = UserService(session_service=object())
    service._project_repo = _ProjectRepo()
    token = set_locale(locale)
    try:
        result = await service.upload_user_project_files(
            user_id="keycloak-subject",
            files=[_Upload("unsafe.html", "text/html", b"<html>unsafe</html>")],
            project_id=None,
            temp_id_map_raw=None,
        )
    finally:
        reset_locale(token)
    assert result["user_files"] == []
    expected = "Uploaded file type is not supported." if locale == "en" else "Yüklenen dosya türü desteklenmiyor."
    assert result["rejected_files"] == [{"name": "unsafe.html", "reason": expected}]
