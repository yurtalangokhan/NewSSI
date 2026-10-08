"""UserServiceClient's mutating calls never sent an Idempotency-Key.

user-service's idempotency middleware requires one on several internal
write routes (REQUIRED_REPLAY policy + IDEMPOTENCY_ENFORCE_REQUIRED_KEYS=True
by default -- see user-service's core/idempotency.py), and rejects a request
missing it with 400 before the route handler ever runs. Every mutating
UserServiceClient call (batch user lookup, memory CRUD, prompt-shortcut
CRUD, profile/settings updates, Keycloak upsert) hit this, silently, because
callers like persona_service.py swallow the resulting ApplicationError
and just log a warning.
"""

import asyncio
import uuid

import httpx
from error_contract import ConfigurationError
import pytest
from security import reset_policy_cache

from integrations import user_service_client as UserServiceClient
from tests.envelope import envelope


@pytest.fixture(autouse=True)
def _fresh_policy(monkeypatch, shared_http_clients):
    reset_policy_cache()
    shared_http_clients()
    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", "http://user-service")
    yield
    shared_http_clients()
    reset_policy_cache()


def _capture_headers_transport(captured: list[httpx.Headers], *, failures: int = 0):
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        captured.append(request.headers)
        if calls["n"] <= failures:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=envelope({"ok": True}))

    return httpx.MockTransport(handler)


def _patch_transport(monkeypatch, transport):
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


def test_user_service_base_url_uses_internal_value_when_public_value_conflicts(monkeypatch):
    monkeypatch.setenv("USER_SERVICE_URL", "https://public-users.example")
    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", "http://user-service:8080/")

    assert UserServiceClient._user_service_base_url() == "http://user-service:8080"


def test_missing_internal_user_service_url_fails_clearly(monkeypatch):
    monkeypatch.delenv("INTERNAL_USER_SERVICE_URL")
    monkeypatch.setenv("USER_SERVICE_URL", "https://public-users.example")

    with pytest.raises(ConfigurationError):
        UserServiceClient._user_service_base_url()


def test_mutating_request_carries_an_idempotency_key(monkeypatch) -> None:
    captured: list[httpx.Headers] = []
    _patch_transport(monkeypatch, _capture_headers_transport(captured))

    asyncio.run(
        UserServiceClient._request(
            "POST",
            "/api/v1/internal/users/batch",
            json_body={"user_ids": []},
        )
    )

    assert len(captured) == 1
    key = captured[0].get("idempotency-key")
    assert key, "POST to a REQUIRED_REPLAY route must carry an Idempotency-Key"
    uuid.UUID(key)  # must be a well-formed key, not a placeholder string


def test_get_request_carries_no_idempotency_key(monkeypatch) -> None:
    captured: list[httpx.Headers] = []
    _patch_transport(monkeypatch, _capture_headers_transport(captured))

    asyncio.run(UserServiceClient._request("GET", "/api/v1/internal/users/u1/settings"))

    assert len(captured) == 1
    assert "idempotency-key" not in captured[0]


def test_permission_check_post_carries_no_idempotency_key(monkeypatch) -> None:
    captured: list[httpx.Headers] = []
    _patch_transport(monkeypatch, _capture_headers_transport(captured))

    asyncio.run(UserServiceClient.authorize_user_permission("user-1", "provider:read"))

    assert len(captured) == 1
    assert "idempotency-key" not in captured[0]


def test_retry_of_the_same_call_reuses_one_idempotency_key(monkeypatch) -> None:
    """A transient-failure retry must replay under the same key.

    Otherwise a network blip during a write turns one logical operation into
    two distinct idempotency keys at user-service, defeating the whole point
    of sending one: a duplicate write goes through instead of being deduped.
    """
    captured: list[httpx.Headers] = []
    _patch_transport(monkeypatch, _capture_headers_transport(captured, failures=2))

    asyncio.run(
        UserServiceClient._request(
            "POST",
            "/api/v1/internal/users/u1/memories",
            json_body={"content": "x"},
        )
    )

    assert len(captured) == 3, "expected two retries before the successful call"
    keys = {headers.get("idempotency-key") for headers in captured}
    assert len(keys) == 1, "all attempts of one logical call must share one key"
