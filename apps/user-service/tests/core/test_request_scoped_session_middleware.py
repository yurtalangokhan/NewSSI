"""Spec T5: the middleware that owns commit/rollback for the one session
shared by every repository call within a single HTTP request.

Policy: a response with status < 400 commits (the request's work is kept as
one transaction); anything else -- a 4xx/5xx response, or an exception that
propagates past the router entirely -- rolls the whole request back. This is
strictly more correct than the old call-scoped-session behaviour, where an
earlier repository call's write was already committed by the time a later
call in the same logical operation failed.

The session is opened lazily by whichever route handler actually calls
``get_current_scope().get_or_open()`` (standing in for a real repository
call) -- a route that never touches one must never open a real DB
connection, and there is nothing for the middleware to commit or roll back.
"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import src.core.database.engine as engine_module
from src.core.database.engine import get_current_scope, get_current_session
from src.core.database.middleware import RequestScopedSessionMiddleware


class _FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def close(self):
        self.closed = True


def _build_app(sessions: list):
    """sessions collects every _FakeSession the factory hands out, in order."""

    def _fake_factory():
        session = _FakeSession()
        sessions.append(session)
        return session

    app = FastAPI()
    app.add_middleware(RequestScopedSessionMiddleware)

    @app.get("/ok")
    async def ok():
        # Stands in for a repository call touching the shared session.
        get_current_scope().get_or_open()
        return {"status": "ok"}

    @app.get("/ok-no-db")
    async def ok_no_db():
        return {"status": "ok"}

    @app.get("/forbidden")
    async def forbidden():
        get_current_scope().get_or_open()
        raise HTTPException(status_code=403, detail="nope")

    @app.get("/boom")
    async def boom():
        get_current_scope().get_or_open()
        raise RuntimeError("boom")

    return app, _fake_factory


@pytest.fixture
def client(monkeypatch):
    sessions: list[_FakeSession] = []
    app, fake_factory = _build_app(sessions)
    monkeypatch.setattr(engine_module, "get_session_factory", lambda: fake_factory)
    test_client = TestClient(app, raise_server_exceptions=False)
    return test_client, sessions


def test_a_successful_response_commits(client):
    test_client, sessions = client
    response = test_client.get("/ok")

    assert response.status_code == 200
    assert len(sessions) == 1
    assert sessions[0].commits == 1
    assert sessions[0].rollbacks == 0
    assert sessions[0].closed is True


def test_a_route_that_never_touches_the_db_opens_no_session(client):
    test_client, sessions = client
    response = test_client.get("/ok-no-db")

    assert response.status_code == 200
    assert sessions == []


def test_a_handled_4xx_response_rolls_back_instead_of_committing(client):
    test_client, sessions = client
    response = test_client.get("/forbidden")

    assert response.status_code == 403
    assert len(sessions) == 1
    assert sessions[0].commits == 0
    assert sessions[0].rollbacks == 1


def test_an_unhandled_exception_rolls_back_and_still_propagates(client):
    test_client, sessions = client
    response = test_client.get("/boom")

    assert response.status_code == 500
    assert len(sessions) == 1
    assert sessions[0].commits == 0
    assert sessions[0].rollbacks == 1


def test_current_scope_is_not_visible_outside_the_request(client):
    test_client, _sessions = client
    assert get_current_session() is None
    assert get_current_scope() is None
    test_client.get("/ok")
    assert get_current_session() is None
    assert get_current_scope() is None


def test_sequential_requests_each_get_their_own_session(client):
    test_client, sessions = client
    test_client.get("/ok")
    test_client.get("/ok")

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert sessions[0].commits == 1
    assert sessions[1].commits == 1


def test_non_http_scopes_are_passed_through_untouched(monkeypatch):
    """The middleware must not try to open a DB session for lifespan events."""
    sessions: list[_FakeSession] = []

    @asynccontextmanager
    async def _fake_session_cm():
        session = _FakeSession()
        sessions.append(session)
        yield session

    monkeypatch.setattr(engine_module, "get_session_factory", lambda: lambda: _fake_session_cm())

    app = FastAPI()
    app.add_middleware(RequestScopedSessionMiddleware)

    with TestClient(app):
        # The lifespan startup/shutdown handshake happens on __enter__/__exit__
        # above; a plain app with no lifespan hooks does nothing there, but if
        # our middleware mishandled the "lifespan" scope type it would raise
        # instead of getting this far.
        pass

    assert sessions == []
