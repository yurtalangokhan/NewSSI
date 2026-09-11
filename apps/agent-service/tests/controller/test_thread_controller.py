"""Tests for ThreadController exclusion filters (P7 Task 42).

Spec: .tmp/flow-canvas-design.md section 6.1.
Brief: .tmp/flow-canvas-task-42-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from controller.thread_controller import ThreadController


@pytest.mark.asyncio
async def test_list_threads_excludes_playground_by_default():
    """42.1 — list_threads defaults to run_kinds=('production',), excluding playground."""
    controller = ThreadController()
    with patch(
        "controller.thread_controller.list_threads_from_store", new_callable=AsyncMock
    ) as mock_list:
        mock_list.return_value = [{"thread_id": "t1", "run_kind": "production"}]

        res = await controller.list_threads()
        mock_list.assert_awaited_once_with(100, 0, None, run_kinds=("production",))
        assert len(res) == 1
        assert res[0]["run_kind"] == "production"


@pytest.mark.asyncio
async def test_list_threads_can_include_playground_explicitly():
    """42.2 — list_threads accepts explicit run_kinds parameter override."""
    controller = ThreadController()
    with patch(
        "controller.thread_controller.list_threads_from_store", new_callable=AsyncMock
    ) as mock_list:
        mock_list.return_value = [
            {"thread_id": "t1", "run_kind": "production"},
            {"thread_id": "t2", "run_kind": "playground"},
        ]

        res = await controller.list_threads(run_kinds=("production", "playground"))
        mock_list.assert_awaited_once_with(100, 0, None, run_kinds=("production", "playground"))
        assert len(res) == 2


@pytest.mark.asyncio
async def test_list_chat_sessions_excludes_playground_by_default():
    """42.3 — list_chat_sessions_by_activity defaults to run_kinds=('production',)."""
    controller = ThreadController()
    with patch(
        "controller.thread_controller.list_chat_sessions_by_activity_from_store",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = [{"thread_id": "t1", "run_kind": "production"}]

        res = await controller.list_chat_sessions_by_activity()
        mock_list.assert_awaited_once_with(100, None, None, None, run_kinds=("production",))
        assert len(res) == 1


@pytest.mark.asyncio
async def test_store_service_forwards_run_kinds():
    """42.4 — StoreService wrapper functions pass run_kinds to ThreadRepository."""
    from service.StoreService import (
        list_chat_sessions_by_activity_from_store,
        list_threads_from_store,
    )

    with patch("service.StoreService._thread_repo") as mock_repo_fn:
        mock_repo = AsyncMock()
        mock_repo_fn.return_value = mock_repo

        await list_threads_from_store(50, 10, {"user_id": "u1"}, run_kinds=("production",))
        mock_repo.list_threads.assert_awaited_once_with(
            limit=50, offset=10, metadata_filter={"user_id": "u1"}, run_kinds=("production",)
        )

        await list_chat_sessions_by_activity_from_store(
            20, "2026-08-14", "id1", {"user_id": "u1"}, run_kinds=("production",)
        )
        mock_repo.list_chat_sessions_by_activity.assert_awaited_once_with(
            page_size=20,
            before_activity="2026-08-14",
            before_id="id1",
            metadata_filter={"user_id": "u1"},
            run_kinds=("production",),
        )


@pytest.mark.asyncio
async def test_repository_default_stays_unfiltered():
    """42.5 — ThreadRepository itself defaults run_kinds to None (unfiltered)."""
    import inspect

    from core.db.repositories.thread_repo import ThreadRepository

    sig = inspect.signature(ThreadRepository.list_threads)
    assert sig.parameters["run_kinds"].default is None

    sig_chat = inspect.signature(ThreadRepository.list_chat_sessions_by_activity)
    assert sig_chat.parameters["run_kinds"].default is None
