"""A chat file belongs to the user who uploaded it.

`document_repo.get_by_file_id` looked a file up by id alone, and the
in-memory `FileRecord` carried no owner at all, so any authenticated caller
who knew (or guessed) a file id could download another user's upload through
`/api/chat/file/{file_id}` — and the same repository call also fed
ChatFileContextService, which would put those bytes into the LLM context of
whoever asked.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routes.file_route import get_chat_file
from service.auth.auth_service import AuthenticatedUser
from service.storage.file_service import store_file

OWNER = AuthenticatedUser(user_id="owner-1", email="owner@example.com")
ATTACKER = AuthenticatedUser(user_id="attacker-9", email="attacker@example.com")


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.storage.file_service import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    """Nothing in these tests should fall through to a real document row."""

    class _EmptyRepo:
        async def get_by_file_id(self, file_id, user_id):
            return None

    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository", _EmptyRepo
    )


@pytest.mark.asyncio
async def test_owner_can_read_their_own_cached_file():
    store_file("file-1", b"hello", "text/plain", "notes.txt", owner_id=OWNER.user_id)

    response = await get_chat_file("file-1", user=OWNER)

    assert response.body == b"hello"


@pytest.mark.asyncio
async def test_another_user_cannot_read_a_cached_file():
    store_file("file-1", b"hello", "text/plain", "notes.txt", owner_id=OWNER.user_id)

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_file("file-1", user=ATTACKER)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_an_unowned_cached_file_is_not_served_without_a_matching_document_row():
    """Records cached without an owner (history rehydration) must still be
    cleared by the authoritative document row rather than served blindly."""
    store_file("file-1", b"hello", "text/plain", "notes.txt")

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_file("file-1", user=ATTACKER)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_the_database_lookup_is_scoped_to_the_caller(monkeypatch):
    seen: dict[str, object] = {}

    class _RecordingRepo:
        async def get_by_file_id(self, file_id, user_id):
            seen["file_id"] = file_id
            seen["user_id"] = user_id
            return None

    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository", _RecordingRepo
    )

    with pytest.raises(HTTPException):
        await get_chat_file("file-2", user=ATTACKER)

    assert seen == {"file_id": "file-2", "user_id": ATTACKER.user_id}
