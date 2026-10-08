"""Spec: production (non-playground) threads get NO automatic checkpoint
retention today -- only playground runs are swept. This generalizes
PlaygroundRetentionWorker.sweep_once to also sweep production threads when
PRODUCTION_RETENTION_DAYS is configured, using inactivity (not creation
time) as the cutoff. Off by default: unlike playground runs, deleting a
user's real chat history is a consequential default to opt into.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from service.runtime.playground_retention_service import PlaygroundRetentionWorker


@pytest.mark.asyncio
async def test_production_retention_is_off_by_default(monkeypatch):
    monkeypatch.delenv("PRODUCTION_RETENTION_DAYS", raising=False)

    delete_expired = AsyncMock(return_value=[])
    delete_inactive = AsyncMock(return_value=[])
    worker = PlaygroundRetentionWorker(
        delete_expired=delete_expired, delete_inactive=delete_inactive
    )

    await worker.sweep_once()

    delete_inactive.assert_not_awaited()


@pytest.mark.asyncio
async def test_production_retention_sweeps_inactive_threads_when_enabled(monkeypatch):
    monkeypatch.setenv("PRODUCTION_RETENTION_DAYS", "90")

    delete_expired = AsyncMock(return_value=[])
    delete_inactive = AsyncMock(return_value=[])
    worker = PlaygroundRetentionWorker(
        delete_expired=delete_expired, delete_inactive=delete_inactive
    )

    await worker.sweep_once()

    delete_inactive.assert_awaited_once()
    run_kind, cutoff = delete_inactive.call_args[0]
    assert run_kind == "production"
    diff = datetime.now(UTC) - cutoff
    assert 89 <= diff.days <= 91


@pytest.mark.asyncio
async def test_production_sweep_still_purges_checkpointer_state(monkeypatch):
    monkeypatch.setenv("PRODUCTION_RETENTION_DAYS", "90")

    delete_expired = AsyncMock(return_value=[])
    t1 = str(uuid4())
    delete_inactive = AsyncMock(return_value=[t1])

    mock_saver = AsyncMock()
    worker = PlaygroundRetentionWorker(
        delete_expired=delete_expired, delete_inactive=delete_inactive
    )

    with patch("service.runtime.playground_retention_service.get_checkpointer", return_value=mock_saver):
        deleted = await worker.sweep_once()

    assert deleted == [t1]
    mock_saver.adelete_thread.assert_awaited_once_with(t1)


@pytest.mark.asyncio
async def test_sweep_combines_playground_and_production_results(monkeypatch):
    monkeypatch.setenv("PRODUCTION_RETENTION_DAYS", "90")

    playground_id, production_id = str(uuid4()), str(uuid4())
    delete_expired = AsyncMock(return_value=[playground_id])
    delete_inactive = AsyncMock(return_value=[production_id])
    worker = PlaygroundRetentionWorker(
        delete_expired=delete_expired, delete_inactive=delete_inactive
    )

    with patch("service.runtime.playground_retention_service.get_checkpointer", return_value=AsyncMock()):
        deleted = await worker.sweep_once()

    assert set(deleted) == {playground_id, production_id}


@pytest.mark.asyncio
async def test_a_production_purge_failure_does_not_abort_the_sweep(monkeypatch):
    monkeypatch.setenv("PRODUCTION_RETENTION_DAYS", "90")

    delete_expired = AsyncMock(return_value=[])
    t1 = str(uuid4())
    delete_inactive = AsyncMock(return_value=[t1])

    mock_saver = AsyncMock()
    mock_saver.adelete_thread = AsyncMock(side_effect=Exception("DB error"))
    worker = PlaygroundRetentionWorker(
        delete_expired=delete_expired, delete_inactive=delete_inactive
    )

    with patch("service.runtime.playground_retention_service.get_checkpointer", return_value=mock_saver):
        # Must not raise -- checkpoint purge is best-effort, same as the
        # existing playground behavior.
        deleted = await worker.sweep_once()

    assert deleted == [t1]
