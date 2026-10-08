"""Tests for ThreadAccessService exclusion filters (P7 Task 42).

Spec: .tmp/flow-canvas-design.md section 6.1.
Brief: .tmp/flow-canvas-task-42-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from service.threads.thread_access_service import ThreadAccessService


@pytest.mark.asyncio
async def test_list_threads_excludes_playground_by_default():
    """42.1 — list_threads defaults to run_kinds=('production',), excluding playground."""
    service = ThreadAccessService()
    with patch(
        "service.threads.thread_access_service.list_threads_from_store", new_callable=AsyncMock
    ) as mock_list:
        mock_list.return_value = [{"thread_id": "t1", "run_kind": "production"}]

        res = await service.list_threads()
        mock_list.assert_awaited_once_with(
            100, 0, None, metadata_any=None, run_kinds=("production",)
        )
        assert len(res) == 1
        assert res[0]["run_kind"] == "production"


@pytest.mark.asyncio
async def test_list_threads_can_include_playground_explicitly():
    """42.2 — list_threads accepts explicit run_kinds parameter override."""
    service = ThreadAccessService()
    with patch(
        "service.threads.thread_access_service.list_threads_from_store", new_callable=AsyncMock
    ) as mock_list:
        mock_list.return_value = [
            {"thread_id": "t1", "run_kind": "production"},
            {"thread_id": "t2", "run_kind": "playground"},
        ]

        res = await service.list_threads(run_kinds=("production", "playground"))
        mock_list.assert_awaited_once_with(
            100, 0, None, metadata_any=None, run_kinds=("production", "playground")
        )
        assert len(res) == 2


@pytest.mark.asyncio
async def test_list_chat_sessions_excludes_playground_by_default():
    """42.3 — list_chat_sessions_by_activity defaults to run_kinds=('production',)."""
    service = ThreadAccessService()
    with patch(
        "service.threads.thread_access_service.list_chat_sessions_by_activity_from_store",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = [{"thread_id": "t1", "run_kind": "production"}]

        res = await service.list_chat_sessions_by_activity()
        mock_list.assert_awaited_once_with(
            100,
            None,
            None,
            None,
            metadata_any=None,
            run_kinds=("production",),
            name_contains=None,
            agents_only=False,
        )
        assert len(res) == 1


@pytest.mark.asyncio
async def test_list_chat_sessions_forwards_search_and_agent_filters():
    service = ThreadAccessService()
    with patch(
        "service.threads.thread_access_service.list_chat_sessions_by_activity_from_store",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = []

        await service.list_chat_sessions_by_activity(name_contains="x", agents_only=True)

        kwargs = mock_list.await_args.kwargs
        assert kwargs["name_contains"] == "x"
        assert kwargs["agents_only"] is True


@pytest.mark.asyncio
async def test_store_service_forwards_search_and_agent_filters_to_the_repository():
    from service.runtime.store_service import list_chat_sessions_by_activity_from_store

    with patch("service.runtime.store_service._thread_repo") as mock_repo_fn:
        mock_repo = AsyncMock()
        mock_repo.list_chat_sessions_by_activity.return_value = []
        mock_repo_fn.return_value = mock_repo

        await list_chat_sessions_by_activity_from_store(name_contains="x", agents_only=True)

        kwargs = mock_repo.list_chat_sessions_by_activity.await_args.kwargs
        assert kwargs["name_contains"] == "x"
        assert kwargs["agents_only"] is True


@pytest.mark.asyncio
async def test_store_service_forwards_run_kinds():
    """42.4 — StoreService wrapper functions pass run_kinds to ThreadRepository."""
    from service.runtime.store_service import (
        list_chat_sessions_by_activity_from_store,
        list_threads_from_store,
    )

    with patch("service.runtime.store_service._thread_repo") as mock_repo_fn:
        mock_repo = AsyncMock()
        mock_repo_fn.return_value = mock_repo

        await list_threads_from_store(50, 10, {"user_id": "u1"}, run_kinds=("production",))
        mock_repo.list_threads.assert_awaited_once_with(
            limit=50,
            offset=10,
            metadata_filter={"user_id": "u1"},
            metadata_filter_any=None,
            run_kinds=("production",),
        )

        await list_chat_sessions_by_activity_from_store(
            20, "2026-08-14", "id1", {"user_id": "u1"}, run_kinds=("production",)
        )
        mock_repo.list_chat_sessions_by_activity.assert_awaited_once_with(
            page_size=20,
            before_activity="2026-08-14",
            before_id="id1",
            metadata_filter={"user_id": "u1"},
            metadata_filter_any=None,
            run_kinds=("production",),
            name_contains=None,
            agents_only=False,
        )


@pytest.mark.asyncio
async def test_repository_default_stays_unfiltered():
    """42.5 — ThreadRepository itself defaults run_kinds to None (unfiltered)."""
    import inspect

    from infrastructure.db.repositories.thread_repo import ThreadRepository

    sig = inspect.signature(ThreadRepository.list_threads)
    assert sig.parameters["run_kinds"].default is None

    sig_chat = inspect.signature(ThreadRepository.list_chat_sessions_by_activity)
    assert sig_chat.parameters["run_kinds"].default is None


@pytest.mark.asyncio
async def test_delete_thread_also_purges_the_checkpoint():
    """B13 — deleting only the message rows left the LangGraph checkpoint
    behind, so reusing the same session id resurrected the old conversation.
    delete_thread must purge both."""
    service = ThreadAccessService()
    saver = AsyncMock()
    with (
        patch(
            "service.threads.thread_access_service.delete_thread_from_store",
            new=AsyncMock(return_value=True),
        ) as store_del,
        patch("service.threads.thread_access_service.get_checkpointer", return_value=saver),
    ):
        ok = await service.delete_thread("thread-42")

    assert ok is True
    store_del.assert_awaited_once_with("thread-42")
    saver.adelete_thread.assert_awaited_once_with("thread-42")


@pytest.mark.asyncio
async def test_delete_thread_survives_a_checkpoint_purge_failure():
    service = ThreadAccessService()
    saver = AsyncMock()
    saver.adelete_thread.side_effect = RuntimeError("checkpointer down")
    with (
        patch(
            "service.threads.thread_access_service.delete_thread_from_store",
            new=AsyncMock(return_value=True),
        ),
        patch("service.threads.thread_access_service.get_checkpointer", return_value=saver),
    ):
        ok = await service.delete_thread("thread-7")

    assert ok is True  # row deletion still counts
