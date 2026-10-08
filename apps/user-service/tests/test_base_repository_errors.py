from unittest.mock import AsyncMock

import pytest
from error_contract import (
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseTimeoutError,
)
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from src.repository import base_repository
from src.repository.base_repository import BaseRepository


def _session_factory(monkeypatch: pytest.MonkeyPatch, commit_error: Exception | None = None):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False
    if commit_error:
        session.commit.side_effect = commit_error
    monkeypatch.setattr(base_repository.db_engine, "get_session_factory", lambda: lambda: session)
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sdk_error", "contract_error"),
    [
        (SQLAlchemyTimeoutError("pool timeout"), DatabaseTimeoutError),
        (
            DBAPIError("select 1", {}, ConnectionError("closed"), connection_invalidated=True),
            DatabaseConnectionError,
        ),
        (SQLAlchemyError("statement failed"), DatabaseOperationError),
    ],
)
async def test_session_maps_sqlalchemy_failures_after_rollback(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error: Exception,
    contract_error: type[Exception],
):
    session = _session_factory(monkeypatch, sdk_error)

    with pytest.raises(contract_error):
        async with BaseRepository()._session():
            pass

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_rolls_back_and_propagates_unrelated_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    session = _session_factory(monkeypatch)

    with pytest.raises(RuntimeError, match="domain failure"):
        async with BaseRepository()._session():
            raise RuntimeError("domain failure")

    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_scoped_failure_is_mapped_without_repository_rollback(monkeypatch):
    from types import SimpleNamespace

    session = AsyncMock()
    scope = SimpleNamespace(get_or_open=lambda: session)
    monkeypatch.setattr(base_repository.db_engine, "get_current_scope", lambda: scope)

    with pytest.raises(DatabaseTimeoutError):
        async with BaseRepository()._session():
            raise SQLAlchemyTimeoutError("request-scoped query timeout")

    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
