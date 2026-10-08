"""The chat session list advertises which rows still have a live run."""

import pytest

from service.chat.chat_management_service import ChatManagementService
from service.chat_runs.domain import ChatRun, ChatRunSpec
from tests.service.chat_runs.fakes import build_in_memory_chat_runs


def _thread(thread_id: str, owner: str = "user-1") -> dict:
    return {
        "thread_id": thread_id,
        "metadata": {"user_id": owner, "name": thread_id, "persona_id": 1},
        "created_at": "2026-10-01T09:00:00+00:00",
        "updated_at": "2026-10-01T09:00:00+00:00",
        "last_message_at": "2026-10-01T09:00:00+00:00",
        "last_accessed_at": None,
        "project_id": None,
    }


class _ThreadAccessService:
    def __init__(self, threads: list[dict]) -> None:
        self._threads = threads

    async def list_chat_sessions_by_activity(self, **kwargs):
        return list(self._threads)


async def _register_running_run(registry, thread_id: str, owner: str) -> None:
    run = ChatRun.start(
        run_id=f"run-{thread_id}",
        spec=ChatRunSpec(thread_id=thread_id, owner_user_id=owner, input_preview="q"),
        instance_id="i1",
        now=1.0,
    )
    await registry.try_acquire(run, lease_ttl_seconds=60)


@pytest.mark.asyncio
async def test_active_run_is_marked_on_its_own_row_only():
    runtime = build_in_memory_chat_runs()
    await _register_running_run(runtime.registry, "t-live", "user-1")
    service = ChatManagementService(
        thread_service=_ThreadAccessService([_thread("t-live"), _thread("t-idle")]),
        user_id="user-1",
        chat_runs=runtime.service,
    )

    result = await service.get_chat_sessions()

    by_id = {session["id"]: session for session in result["sessions"]}
    assert by_id["t-live"]["has_active_run"] is True
    assert by_id["t-idle"]["has_active_run"] is False


@pytest.mark.asyncio
async def test_run_owned_by_someone_else_is_not_marked_for_the_caller():
    runtime = build_in_memory_chat_runs()
    await _register_running_run(runtime.registry, "t-other", "someone-else")
    service = ChatManagementService(
        thread_service=_ThreadAccessService([_thread("t-other")]),
        user_id="user-1",
        chat_runs=runtime.service,
    )

    result = await service.get_chat_sessions()

    assert result["sessions"][0]["has_active_run"] is False


@pytest.mark.asyncio
async def test_session_list_stays_up_when_the_run_runtime_is_unavailable():
    class _DownService:
        async def active_thread_ids(self, thread_ids, *, owner_ids):
            raise RuntimeError("chat-run registry unreachable")

    service = ChatManagementService(
        thread_service=_ThreadAccessService([_thread("t-1")]),
        user_id="user-1",
        chat_runs=_DownService(),
    )

    result = await service.get_chat_sessions()

    assert result["sessions"][0]["has_active_run"] is False
