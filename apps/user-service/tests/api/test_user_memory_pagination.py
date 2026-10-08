"""UserMemoryService.list_for_ui fetched every one of a user's memory
facts and paginated with a Python slice (rows[start:end]) -- every page
request re-fetched the whole table regardless of page_size. Spec T4."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.user_memory_service import UserMemoryService


def _service() -> UserMemoryService:
    service = UserMemoryService.__new__(UserMemoryService)
    service.repo = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_list_for_ui_paginates_at_the_database_level():
    service = _service()
    fake_row = MagicMock(time_created=None, time_updated=None)
    service.repo.list_by_user = AsyncMock(return_value=[fake_row])
    service.repo.count = AsyncMock(return_value=123)
    user_id = uuid.uuid4()

    result = await service.list_for_ui(user_id, page=3, page_size=10)

    service.repo.list_by_user.assert_awaited_once_with(user_id, limit=10, offset=20)
    assert result["total"] == 123


@pytest.mark.asyncio
async def test_list_for_ui_does_not_fetch_the_full_table():
    """Regression: the old implementation called list_by_user(user_id)
    with no limit/offset at all, i.e. fetched everything."""
    service = _service()
    service.repo.list_by_user = AsyncMock(return_value=[])
    service.repo.count = AsyncMock(return_value=0)

    await service.list_for_ui(uuid.uuid4(), page=1, page_size=25)

    _args, kwargs = service.repo.list_by_user.call_args
    assert kwargs.get("limit") == 25
