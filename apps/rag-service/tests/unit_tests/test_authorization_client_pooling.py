"""Permission lookups reuse the pooled user-service client.

Every outbound call in AuthorizationClient built its own
``httpx.AsyncClient(timeout=5.0)`` inside an ``async with``, so each
permission check paid a fresh TCP (and TLS) handshake and then threw the
connection away. Permission checks run on the hot path of nearly every
request, and the cache only covers repeats -- a cold cache meant one new
socket per check. The shared per-peer pool already exists and is already
what `auth.py` uses to talk to the same service.
"""

from __future__ import annotations

import inspect

import httpx
import pytest

from src.shared import authorization


class _Response:
    def __init__(self, status_code: int = 200, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self) -> object:
        # user-service answers in the shared response envelope.
        return {
            "statusCode": self.status_code,
            "message": None,
            "data": self._payload,
            "error": None,
        }


class _RecordingClient:
    def __init__(self) -> None:
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.response = _Response(200, {"allowed": True, "is_admin": True})

    async def get(self, url: str, **_kwargs: object) -> _Response:
        self.gets.append(url)
        return self.response

    async def post(self, url: str, **_kwargs: object) -> _Response:
        self.posts.append(url)
        return self.response


@pytest.fixture
def pooled(monkeypatch: pytest.MonkeyPatch) -> _RecordingClient:
    client = _RecordingClient()
    names: list[str] = []
    monkeypatch.setattr(
        authorization,
        "get_shared_client",
        lambda name, **_kw: (names.append(name), client)[1],
    )

    def _no_new_clients(*_args: object, **_kwargs: object):
        raise AssertionError("a per-call httpx.AsyncClient was constructed")

    monkeypatch.setattr(authorization.httpx, "AsyncClient", _no_new_clients)
    client.pool_names = names
    return client


@pytest.mark.asyncio
async def test_is_admin_uses_the_pooled_client(pooled: _RecordingClient):
    assert await authorization.AuthorizationClient().is_admin("user-1") is True

    assert pooled.gets, "no request was made"
    assert pooled.pool_names == ["user-service"]


@pytest.mark.asyncio
async def test_the_permission_decision_uses_the_pooled_client(pooled: _RecordingClient):
    # _fetch_permission_decision rather than has_permission: conftest stubs
    # has_permission for every test in this package, so it never reaches the
    # network leg this test is about.
    client = authorization.AuthorizationClient()

    allowed = await client._fetch_permission_decision(
        user_id="user-1", permission="collection:create", access_token=None
    )

    assert allowed is True
    assert pooled.posts, "no authorize request was made"


@pytest.mark.asyncio
async def test_the_effective_permissions_fallback_uses_the_pooled_client(
    pooled: _RecordingClient,
):
    pooled.response = _Response(500)
    client = authorization.AuthorizationClient()

    # The POST comes back non-200, which drops through to the GET fallback;
    # both legs must go through the pool.
    allowed = await client._fetch_permission_decision(
        user_id="user-1", permission="collection:create", access_token=None
    )

    assert allowed is False
    assert pooled.posts, "the authorize call did not go through the pool"
    assert pooled.gets, "the effective-permissions fallback did not go through the pool"


def test_no_method_opens_its_own_client():
    source = inspect.getsource(authorization.AuthorizationClient)
    assert "httpx.AsyncClient(" not in source
