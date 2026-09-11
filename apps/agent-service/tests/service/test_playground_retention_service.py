"""Tests for PlaygroundRetentionService (P7 Task 43).

Spec: .tmp/flow-canvas-design.md section 6.1 (retention TTL).
Brief: .tmp/flow-canvas-task-43-brief.md
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.db.repositories.thread_repo import ThreadRepository
from service.PlaygroundRetentionService import PlaygroundRetentionWorker


@pytest.mark.asyncio
async def test_delete_threads_older_than_removes_expired_playground_rows():
    """43.1 — delete_threads_older_than returns deleted IDs and filters properly."""
    repo = ThreadRepository()
    mock_session = AsyncMock()
    expired_id = str(uuid4())

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [expired_id]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars

    mock_session.execute = AsyncMock(side_effect=[mock_res, MagicMock()])

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        yield mock_session

    repo._session = fake_session  # type: ignore[method-assign]

    cutoff = datetime.now(UTC) - timedelta(days=30)
    deleted = await repo.delete_threads_older_than(run_kind="playground", older_than=cutoff)

    assert deleted == [expired_id]
    assert mock_session.execute.await_count == 2


@pytest.mark.asyncio
async def test_sweep_purges_checkpointer_state_for_deleted_threads():
    """43.4 — sweep_once calls checkpointer.adelete_thread for each deleted thread_id."""
    mock_repo = AsyncMock()
    t1, t2 = str(uuid4()), str(uuid4())
    mock_repo.delete_threads_older_than.return_value = [t1, t2]

    mock_saver = AsyncMock()
    mock_saver.adelete_thread = AsyncMock()

    worker = PlaygroundRetentionWorker(repo=mock_repo)

    with patch("service.PlaygroundRetentionService.get_checkpointer", return_value=mock_saver):
        deleted = await worker.sweep_once()
        assert deleted == [t1, t2]
        assert mock_saver.adelete_thread.await_count == 2
        mock_saver.adelete_thread.assert_any_await(t1)
        mock_saver.adelete_thread.assert_any_await(t2)


@pytest.mark.asyncio
async def test_sweep_survives_a_single_thread_purge_failure():
    """43.5 — One checkpointer adelete_thread failure does not abort the remaining sweep."""
    mock_repo = AsyncMock()
    t1, t2 = str(uuid4()), str(uuid4())
    mock_repo.delete_threads_older_than.return_value = [t1, t2]

    mock_saver = AsyncMock()
    mock_saver.adelete_thread = AsyncMock(side_effect=[Exception("DB error"), None])

    worker = PlaygroundRetentionWorker(repo=mock_repo)

    with patch("service.PlaygroundRetentionService.get_checkpointer", return_value=mock_saver):
        deleted = await worker.sweep_once()
        assert deleted == [t1, t2]
        assert mock_saver.adelete_thread.await_count == 2


@pytest.mark.asyncio
async def test_retention_days_is_configurable_via_env(monkeypatch: pytest.MonkeyPatch):
    """43.6 — PLAYGROUND_RETENTION_DAYS changes cutoff calculation."""

    monkeypatch.setenv("PLAYGROUND_RETENTION_DAYS", "7")

    mock_repo = AsyncMock()
    mock_repo.delete_threads_older_than.return_value = []
    worker = PlaygroundRetentionWorker(repo=mock_repo)

    await worker.sweep_once()
    mock_repo.delete_threads_older_than.assert_awaited_once()
    call_kwargs = mock_repo.delete_threads_older_than.call_args[1]
    assert call_kwargs["run_kind"] == "playground"
    cutoff = call_kwargs["older_than"]
    # Cutoff should be approximately 7 days ago
    diff = datetime.now(UTC) - cutoff
    assert 6 <= diff.days <= 8


@pytest.mark.asyncio
async def test_worker_start_stop_lifecycle():
    """43.7 — start creates task, stop cancels and awaits."""
    worker = PlaygroundRetentionWorker(repo=AsyncMock())
    worker.start()
    assert worker._running is True
    assert worker._task is not None
    assert not worker._task.done()

    await worker.stop()
    assert worker._running is False
    assert worker._task is None


@pytest.mark.asyncio
async def test_sweep_loop_survives_one_bad_iteration():
    """43.8 — Loop catches exceptions in sweep_once without exiting."""
    worker = PlaygroundRetentionWorker(repo=AsyncMock())
    call_count = 0

    async def fake_sweep():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Transient error")
        await worker.stop()
        return []

    worker.sweep_once = fake_sweep  # type: ignore[method-assign]
    worker._running = True

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await worker._poll_loop()

    assert call_count >= 1
