"""Spec: UserMemoryService.add_facts must enforce the storage cap it reads
for recall, not just cap what's read back. Before this, MAX_FACTS only
bounded list_for_recall's query LIMIT; nothing ever removed old rows, so a
long-lived chatty user's table grew forever.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.user_memory_service import UserMemoryService


def _service() -> UserMemoryService:
    service = UserMemoryService.__new__(UserMemoryService)
    service.repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_add_facts_evicts_the_oldest_rows_beyond_the_cap(monkeypatch):
    service = _service()
    user_id = uuid.uuid4()
    service.repo.bulk_create = AsyncMock(
        return_value=[
            MagicMock(
                id=uuid.uuid4(),
                content="fact",
                source="auto_extracted",
                time_created=None,
                time_updated=None,
            ),
        ]
    )
    service.repo.delete_oldest_excess = AsyncMock(return_value=3)

    monkeypatch.setenv("MEMORY_MAX_FACTS", "50")
    await service.add_facts(user_id, ["a new fact"])

    service.repo.delete_oldest_excess.assert_awaited_once_with(user_id, keep=50)


@pytest.mark.asyncio
async def test_add_facts_does_not_evict_when_nothing_was_created():
    # bulk_create returns [] when every candidate fact was a duplicate
    # (ON CONFLICT DO NOTHING) -- nothing changed, so there's nothing to evict.
    service = _service()
    user_id = uuid.uuid4()
    service.repo.bulk_create = AsyncMock(return_value=[])
    service.repo.delete_oldest_excess = AsyncMock(return_value=0)

    await service.add_facts(user_id, ["a duplicate fact"])

    service.repo.delete_oldest_excess.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_for_recall_uses_the_configured_cap(monkeypatch):
    service = _service()
    user_id = uuid.uuid4()
    service.repo.list_by_user = AsyncMock(return_value=[])

    monkeypatch.setenv("MEMORY_MAX_FACTS", "123")
    await service.list_for_recall(user_id)

    service.repo.list_by_user.assert_awaited_once_with(user_id, limit=123)
