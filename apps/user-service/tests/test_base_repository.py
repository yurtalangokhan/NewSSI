"""Spec T5: BaseRepository._session must reuse the request-scoped session
when a request scope is active (so every repository call within one HTTP
request shares a single transaction, owned by the middleware), and fall
back to its own call-scoped session -- committing on success, rolling back
on failure, exactly as before -- outside of a request (startup code,
scripts, tests).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import src.core.database.engine as engine_module
from src.repository.base_repository import BaseRepository


class _FakeSessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


class _FakeScope:
    def __init__(self, session):
        self.session = session

    def get_or_open(self):
        return self.session


@pytest.mark.asyncio
async def test_uses_the_request_scoped_session_when_a_scope_is_active(monkeypatch):
    shared_session = MagicMock()
    shared_session.commit = AsyncMock()
    shared_session.rollback = AsyncMock()
    monkeypatch.setattr(engine_module, "get_current_scope", lambda: _FakeScope(shared_session))

    factory_called = False

    def _factory():
        nonlocal factory_called
        factory_called = True
        raise AssertionError("must not open its own session when a request scope is active")

    monkeypatch.setattr(engine_module, "get_session_factory", _factory)

    repo = BaseRepository()
    async with repo._session() as session:
        assert session is shared_session

    assert not factory_called
    # Ownership of commit/rollback belongs to the middleware that published
    # the shared scope, not to the repository borrowing its session.
    shared_session.commit.assert_not_called()
    shared_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_propagates_exceptions_without_touching_the_shared_session(monkeypatch):
    shared_session = MagicMock()
    shared_session.commit = AsyncMock()
    shared_session.rollback = AsyncMock()
    monkeypatch.setattr(engine_module, "get_current_scope", lambda: _FakeScope(shared_session))

    repo = BaseRepository()
    with pytest.raises(ValueError):
        async with repo._session():
            raise ValueError("boom")

    shared_session.commit.assert_not_called()
    shared_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_falls_back_to_its_own_session_outside_a_request(monkeypatch):
    monkeypatch.setattr(engine_module, "get_current_scope", lambda: None)

    own_session = MagicMock()
    own_session.commit = AsyncMock()
    own_session.rollback = AsyncMock()
    monkeypatch.setattr(
        engine_module, "get_session_factory", lambda: lambda: _FakeSessionCM(own_session)
    )

    repo = BaseRepository()
    async with repo._session() as session:
        assert session is own_session

    own_session.commit.assert_awaited_once()
    own_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_own_session_is_rolled_back_on_failure_outside_a_request(monkeypatch):
    monkeypatch.setattr(engine_module, "get_current_scope", lambda: None)

    own_session = MagicMock()
    own_session.commit = AsyncMock()
    own_session.rollback = AsyncMock()
    monkeypatch.setattr(
        engine_module, "get_session_factory", lambda: lambda: _FakeSessionCM(own_session)
    )

    repo = BaseRepository()
    with pytest.raises(ValueError):
        async with repo._session():
            raise ValueError("boom")

    own_session.commit.assert_not_called()
    own_session.rollback.assert_awaited_once()
