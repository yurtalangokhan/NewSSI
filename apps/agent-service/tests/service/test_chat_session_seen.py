"""The read watermark (`seen`) clears the sidebar's unread dot."""

import pytest

from error_contract import NotFoundError
from service.chat.chat_management_service import ChatManagementService


class _ThreadAccessService:
    def __init__(self, threads: dict[str, dict]) -> None:
        self._threads = threads
        self.accessed: list[str] = []
        self.raise_on_accessed = False

    async def get_thread(self, thread_id: str):
        return self._threads.get(thread_id)

    async def mark_accessed(self, thread_id: str):
        if self.raise_on_accessed:
            raise RuntimeError("thread store unavailable")
        self.accessed.append(thread_id)
        thread = self._threads[thread_id]
        thread["last_accessed_at"] = "2026-10-01T12:00:00+00:00"
        return thread


def _thread(thread_id: str, owner: str = "user-1") -> dict:
    return {
        "thread_id": thread_id,
        "metadata": {"user_id": owner, "name": thread_id, "persona_id": 1},
        "created_at": "2026-10-01T09:00:00+00:00",
        "updated_at": "2026-10-01T09:00:00+00:00",
        "last_message_at": "2026-10-01T10:00:00+00:00",
        "last_accessed_at": "2026-10-01T09:00:00+00:00",
        "project_id": None,
    }


@pytest.mark.asyncio
async def test_seen_advances_the_read_watermark():
    thread = _thread("t1")
    access = _ThreadAccessService({"t1": thread})
    service = ChatManagementService(thread_service=access, user_id="user-1")

    await service.mark_session_seen("t1")

    assert access.accessed == ["t1"]
    assert thread["last_accessed_at"] == "2026-10-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_seen_on_an_unknown_session_is_not_found():
    service = ChatManagementService(thread_service=_ThreadAccessService({}), user_id="user-1")

    with pytest.raises(NotFoundError):
        await service.mark_session_seen("missing")


@pytest.mark.asyncio
async def test_seen_of_a_foreign_session_is_not_found():
    access = _ThreadAccessService({"t1": _thread("t1", owner="someone-else")})
    service = ChatManagementService(thread_service=access, user_id="user-1")

    with pytest.raises(NotFoundError):
        await service.mark_session_seen("t1")
    assert access.accessed == []


@pytest.mark.asyncio
async def test_a_storage_failure_does_not_fail_seen():
    access = _ThreadAccessService({"t1": _thread("t1")})
    access.raise_on_accessed = True
    service = ChatManagementService(thread_service=access, user_id="user-1")

    # Bookkeeping must never surface as an error to the client.
    await service.mark_session_seen("t1")
