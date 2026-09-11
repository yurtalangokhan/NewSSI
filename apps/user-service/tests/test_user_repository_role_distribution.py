"""Tests for UserRepository.count_by_role()."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repository.user_repository import UserRepository


def _repository_with_session(session: MagicMock) -> UserRepository:
    repository = UserRepository()

    @asynccontextmanager
    async def session_context():
        yield session

    repository._session = session_context  # type: ignore[method-assign]
    return repository


def _row_result(rows: list[tuple[str, int]]) -> MagicMock:
    result = MagicMock()
    result.__iter__.return_value = iter(rows)
    return result


@pytest.mark.asyncio
async def test_count_by_role_returns_role_and_count() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_row_result([("enduser", 128), ("admin", 5)]))
    repository = _repository_with_session(session)

    result = await repository.count_by_role()

    assert result == [
        {"role": "enduser", "count": 128},
        {"role": "admin", "count": 5},
    ]


@pytest.mark.asyncio
async def test_count_by_role_returns_empty_list_when_no_users() -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=_row_result([]))
    repository = _repository_with_session(session)

    result = await repository.count_by_role()

    assert result == []
