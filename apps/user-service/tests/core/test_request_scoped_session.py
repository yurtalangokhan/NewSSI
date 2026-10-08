"""Spec T5: repositories must share one session per HTTP request, not open a
new one (and therefore a new pooled connection) for every repository call.

``request_scoped_session`` is the plumbing primitive: it publishes a scope
via a ContextVar so any ``BaseRepository`` instance constructed anywhere
during the request can find it, and cleans up when the block exits --
regardless of success or failure. The session itself is opened lazily, by
whichever repository call (if any) needs it first: a request that never
touches a repository must never open a real DB connection just because it
ran inside the request-scoped middleware -- otherwise routes that fake out
the database for narrow purposes (e.g. a health check with a stand-in
engine) break for reasons unrelated to what they're testing.

Committing/rolling back is deliberately not this module's job: that is an
HTTP-semantics decision (2xx vs. not) that belongs to the middleware
wrapping the whole request.
"""

import pytest

from src.core.database.engine import get_current_scope, get_current_session, request_scoped_session


class _FakeSession:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class _FakeSessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


def test_get_current_session_is_none_outside_any_scope():
    assert get_current_session() is None
    assert get_current_scope() is None


@pytest.mark.asyncio
async def test_entering_the_scope_does_not_open_a_session(monkeypatch):
    import src.core.database.engine as engine_module

    def _fail_if_called():
        raise AssertionError("factory must not be called until a repository asks for a session")

    monkeypatch.setattr(engine_module, "get_session_factory", _fail_if_called)

    async with request_scoped_session() as scope:
        assert scope.session is None
        assert get_current_session() is None

    assert get_current_scope() is None


@pytest.mark.asyncio
async def test_get_or_open_lazily_creates_and_caches_one_session(monkeypatch):
    import src.core.database.engine as engine_module

    fake_session = _FakeSession()
    call_count = {"n": 0}

    def _factory():
        call_count["n"] += 1
        return fake_session

    monkeypatch.setattr(engine_module, "get_session_factory", lambda: _factory)

    async with request_scoped_session() as scope:
        opened = scope.get_or_open()
        assert opened is fake_session
        assert get_current_session() is fake_session

        # A second repository call in the same request reuses it rather
        # than opening (and checking out a pooled connection for) another.
        again = scope.get_or_open()
        assert again is fake_session
        assert call_count["n"] == 1

    assert fake_session.closed is True
    assert get_current_session() is None


@pytest.mark.asyncio
async def test_a_session_that_was_never_opened_is_never_closed(monkeypatch):
    import src.core.database.engine as engine_module

    def _fail_if_called():
        raise AssertionError("factory must not be called: no repository ever asked for a session")

    monkeypatch.setattr(engine_module, "get_session_factory", _fail_if_called)

    async with request_scoped_session():
        pass  # no repository call happened during this request


@pytest.mark.asyncio
async def test_current_scope_is_cleared_even_if_the_block_raises(monkeypatch):
    import src.core.database.engine as engine_module

    fake_session = _FakeSession()
    monkeypatch.setattr(engine_module, "get_session_factory", lambda: lambda: fake_session)

    with pytest.raises(ValueError):
        async with request_scoped_session() as scope:
            scope.get_or_open()
            raise ValueError("boom")

    assert fake_session.closed is True
    assert get_current_scope() is None


@pytest.mark.asyncio
async def test_nested_scopes_restore_the_outer_scope(monkeypatch):
    """Not expected in normal request handling, but nesting must not leak the
    outer scope's session as the "current" one once the inner scope exits."""
    import src.core.database.engine as engine_module

    labels = iter([_FakeSession(), _FakeSession()])
    monkeypatch.setattr(engine_module, "get_session_factory", lambda: lambda: next(labels))

    async with request_scoped_session() as outer:
        outer_session = outer.get_or_open()
        assert get_current_session() is outer_session
        async with request_scoped_session() as inner:
            inner_session = inner.get_or_open()
            assert get_current_session() is inner_session
            assert inner_session is not outer_session
        assert get_current_session() is outer_session

    assert get_current_scope() is None
