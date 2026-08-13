"""Focused behavior coverage for chat session activity semantics."""

from copy import deepcopy

import pytest

from controller.chat_controller import ChatController
from controller.user_controller import UserController


class _ThreadController:
    def __init__(self, threads: list[dict]):
        self.threads = {thread["thread_id"]: deepcopy(thread) for thread in threads}
        self.accessed: list[str] = []
        self.message_activity: list[str] = []
        self.update_calls: list[dict] = []
        self.raise_on_access = False

    async def list_chat_sessions_by_activity(self, **kwargs):
        return list(self.threads.values())

    async def get_thread(self, thread_id: str):
        return self.threads.get(thread_id)

    async def get_thread_state(self, thread_id: str):
        return {"values": {"messages": []}}

    async def mark_accessed(self, thread_id: str):
        if self.raise_on_access:
            raise RuntimeError("access telemetry unavailable")
        self.accessed.append(thread_id)
        thread = self.threads[thread_id]
        thread["last_accessed_at"] = "2026-08-07T12:00:00+00:00"
        return thread

    async def mark_message_activity(self, thread_id: str):
        self.message_activity.append(thread_id)
        return self.threads[thread_id]

    async def update_thread(self, thread_id: str, metadata: dict, update_timestamp: bool = True):
        self.update_calls.append(
            {
                "thread_id": thread_id,
                "metadata": deepcopy(metadata),
                "update_timestamp": update_timestamp,
            }
        )
        self.threads[thread_id]["metadata"] = deepcopy(metadata)
        return self.threads[thread_id]


class _PagedThreadController(_ThreadController):
    def __init__(self, threads: list[dict]):
        super().__init__(threads)
        self._ordered_threads = deepcopy(threads)
        self.activity_calls: list[dict] = []

    async def list_chat_sessions_by_activity(self, **kwargs):
        self.activity_calls.append(deepcopy(kwargs))
        before_activity = kwargs.get("before_activity")
        before_id = kwargs.get("before_id")
        page_size = kwargs.get("page_size", 100)

        start = 0
        if before_activity and before_id:
            for index, thread in enumerate(self._ordered_threads):
                activity = ChatController._activity_time(thread)
                if (activity, thread.get("thread_id") or "") < (before_activity, before_id):
                    start = index
                    break
            else:
                return []

        return deepcopy(self._ordered_threads[start : start + page_size])


def _thread(
    thread_id: str,
    *,
    created_at: str = "2026-08-07T09:00:00+00:00",
    updated_at: str = "2026-08-07T09:00:00+00:00",
    last_message_at: str | None = None,
    project_id: int | None = None,
    owner: str = "user-1",
) -> dict:
    thread = {
        "thread_id": thread_id,
        "metadata": {"user_id": owner, "name": thread_id, "persona_id": 1},
        "created_at": created_at,
        "updated_at": updated_at,
        "last_message_at": last_message_at,
        "last_accessed_at": None,
        "project_id": project_id,
    }
    if project_id is not None:
        thread["metadata"]["project_id"] = project_id
    return thread


def _descending_activity_timestamp(index: int) -> str:
    if index < 40:
        return f"2026-08-07T16:{39 - index:02d}:00+00:00"
    return f"2026-08-07T15:{99 - index:02d}:00+00:00"


@pytest.mark.asyncio
async def test_chat_session_list_orders_by_message_activity_and_returns_cursor():
    threads = [
        _thread(
            "older-message",
            updated_at="2026-08-07T15:00:00+00:00",
            last_message_at="2026-08-07T10:00:00+00:00",
        ),
        _thread(
            "newer-message",
            updated_at="2026-08-07T11:00:00+00:00",
            last_message_at="2026-08-07T14:00:00+00:00",
        ),
        _thread("unsent", created_at="2026-08-07T08:00:00+00:00"),
    ]
    controller = ChatController(thread_controller=_ThreadController(threads), user_id="user-1")

    result = await controller.get_chat_sessions(page_size=2)

    assert [session["id"] for session in result["sessions"]] == [
        "newer-message",
        "older-message",
    ]
    assert result["has_more"] is True
    assert result["next_cursor"] == {
        "before_activity": "2026-08-07T10:00:00+00:00",
        "before_id": "older-message",
    }
    assert result["sessions"][0]["last_message_at"] == "2026-08-07T14:00:00+00:00"
    assert result["sessions"][0]["last_accessed_at"] is None


@pytest.mark.asyncio
async def test_chat_session_list_uses_updated_at_only_for_legacy_records():
    legacy = _thread("a-legacy", updated_at="2026-08-07T14:00:00+00:00")
    legacy.pop("last_message_at")
    current_unsent = _thread(
        "z-current-unsent",
        created_at="2026-08-07T10:00:00+00:00",
        updated_at="2026-08-07T16:00:00+00:00",
    )
    controller = ChatController(
        thread_controller=_ThreadController([current_unsent, legacy]), user_id="user-1"
    )

    result = await controller.get_chat_sessions()

    assert [session["id"] for session in result["sessions"]] == [
        "a-legacy",
        "z-current-unsent",
    ]


@pytest.mark.asyncio
async def test_multi_owner_chat_session_list_paginates_until_owner_matches():
    threads = [
        *[
            _thread(
                f"other-{index:03d}",
                owner="other-user",
                last_message_at=_descending_activity_timestamp(index),
            )
            for index in range(100)
        ],
        _thread(
            "legacy-owned",
            owner="keycloak-subject",
            last_message_at="2026-08-07T15:00:00+00:00",
        ),
    ]
    thread_controller = _PagedThreadController(threads)
    controller = ChatController(
        thread_controller=thread_controller,
        user_id="local-user",
        owner_ids=["local-user", "keycloak-subject"],
    )

    result = await controller.get_chat_sessions(page_size=1)

    assert [session["id"] for session in result["sessions"]] == ["legacy-owned"]
    assert thread_controller.activity_calls == [
        {
            "page_size": 100,
            "before_activity": None,
            "before_id": None,
        },
        {
            "page_size": 100,
            "before_activity": "2026-08-07T15:00:00+00:00",
            "before_id": "other-099",
        },
    ]


@pytest.mark.asyncio
async def test_fetch_chat_records_access_without_message_activity_and_repairs_owner_without_update_time():
    thread = _thread("thread-1", owner="")
    controller_thread = _ThreadController([thread])
    controller = ChatController(thread_controller=controller_thread, user_id="user-1")

    result = await controller.get_chat_session("thread-1")

    assert controller_thread.accessed == ["thread-1"]
    assert controller_thread.message_activity == []
    assert controller_thread.update_calls[0]["update_timestamp"] is False
    assert result["last_message_at"] is None
    assert result["last_accessed_at"] == "2026-08-07T12:00:00+00:00"


@pytest.mark.asyncio
async def test_access_tracking_failure_does_not_fail_chat_read():
    controller_thread = _ThreadController([_thread("thread-1")])
    controller_thread.raise_on_access = True
    controller = ChatController(thread_controller=controller_thread, user_id="user-1")

    result = await controller.get_chat_session("thread-1")

    assert result["chat_session_id"] == "thread-1"
    assert controller_thread.message_activity == []


@pytest.mark.asyncio
async def test_metadata_changes_do_not_mark_message_activity():
    controller_thread = _ThreadController([_thread("thread-1")])
    controller = ChatController(thread_controller=controller_thread, user_id="user-1")

    await controller.rename_chat_session("thread-1", "Renamed")
    await controller.update_chat_session_model("thread-1", "model-x")
    await controller.update_chat_session_temperature("thread-1", 0.3)

    assert controller_thread.message_activity == []


class _ProjectRepo:
    async def list_by_user_ids(self, _owner_ids: list[str]) -> list[dict]:
        return [{"id": 7, "user_id": "user-1", "name": "Project"}]

    async def get_for_user_ids(self, _owner_ids: list[str], project_id: int) -> dict:
        return {"id": project_id, "user_id": "user-1", "name": "Project"}


@pytest.mark.asyncio
async def test_project_chat_sessions_order_by_message_activity(monkeypatch):
    threads = [
        _thread(
            "older-message",
            project_id=7,
            updated_at="2026-08-07T16:00:00+00:00",
            last_message_at="2026-08-07T10:00:00+00:00",
        ),
        _thread(
            "newer-message",
            project_id=7,
            updated_at="2026-08-07T11:00:00+00:00",
            last_message_at="2026-08-07T14:00:00+00:00",
        ),
    ]

    async def fake_list_chat_sessions_by_activity_from_store(**_kwargs):
        return threads

    monkeypatch.setattr(
        "controller.user_controller.list_chat_sessions_by_activity_from_store",
        fake_list_chat_sessions_by_activity_from_store,
    )
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()

    project = await controller.get_user_project("user-1", 7)

    assert [session["id"] for session in project["chat_sessions"]] == [
        "newer-message",
        "older-message",
    ]
    assert project["chat_sessions"][0]["last_message_at"] == "2026-08-07T14:00:00+00:00"
    assert project["chat_sessions"][0]["last_accessed_at"] is None


@pytest.mark.asyncio
async def test_project_chat_sessions_paginates_before_filtering_owner(monkeypatch):
    threads = [
        *[
            _thread(
                f"other-{index:03d}",
                project_id=7,
                owner="other-user",
                last_message_at=_descending_activity_timestamp(index),
            )
            for index in range(100)
        ],
        _thread(
            "legacy-owned",
            project_id=7,
            owner="keycloak-subject",
            last_message_at="2026-08-07T15:00:00+00:00",
        ),
    ]
    calls: list[dict] = []

    async def fake_list_chat_sessions_by_activity_from_store(**kwargs):
        calls.append(deepcopy(kwargs))
        before_activity = kwargs.get("before_activity")
        page_size = kwargs.get("page_size", 100)
        if before_activity is None:
            return threads[:page_size]
        return threads[page_size : page_size * 2]

    monkeypatch.setattr(
        "controller.user_controller.list_chat_sessions_by_activity_from_store",
        fake_list_chat_sessions_by_activity_from_store,
    )
    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepo()

    project = await controller.get_user_project(
        "local-user",
        7,
        owner_ids=["local-user", "keycloak-subject"],
    )

    assert [session["id"] for session in project["chat_sessions"]] == ["legacy-owned"]
    assert calls == [
        {
            "page_size": 100,
            "before_activity": None,
            "before_id": None,
        },
        {
            "page_size": 100,
            "before_activity": "2026-08-07T15:00:00+00:00",
            "before_id": "other-099",
        },
    ]


@pytest.mark.asyncio
async def test_project_membership_changes_do_not_mark_message_activity():
    class _ProjectRepoWithMoves(_ProjectRepo):
        async def move_chat_session_to_project_for_user_ids(self, **_kwargs):
            return True

        async def remove_chat_session_from_project_for_user_ids(self, **_kwargs):
            return True

    controller = UserController(session_controller=object())
    controller._project_repo = _ProjectRepoWithMoves()

    assert await controller.move_chat_session_to_project(
        user_id="user-1",
        project_id=7,
        chat_session_id="thread-1",
    ) == {"success": True}
    assert await controller.remove_chat_session_from_project(
        user_id="user-1",
        chat_session_id="thread-1",
    ) == {"success": True}
