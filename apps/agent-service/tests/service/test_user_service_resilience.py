"""Outbound calls to user-service must be both retried and circuit-broken.

The policy file declared a retry budget that nothing applied: ``bounded_retry``
existed but no call site used it, so a single dropped connection surfaced to the
caller as a dependency failure.
"""

import asyncio

import httpx
import pytest
from error_contract import DependencyUnavailableError
from security.resilience import CircuitBreakerOpenError, get_circuit_breaker, reset_policy_cache

from integrations import user_service_client as UserServiceClient
from tests.envelope import envelope


@pytest.fixture(autouse=True)
def _fresh_policy(monkeypatch, shared_http_clients):
    reset_policy_cache()
    # get_shared_client pools one httpx.AsyncClient per peer name for the
    # life of the process; without closing it here, a test's mocked
    # transport (baked in at client construction) would leak into every
    # test that runs after it instead of picking up this test's own patch.
    shared_http_clients()
    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", "http://user-service")
    yield
    shared_http_clients()
    reset_policy_cache()


def _respond(*, failures: int, counter: dict):
    """A transport that fails `failures` times, then succeeds."""

    async def handler(request: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        if counter["calls"] <= failures:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=envelope({"ok": True}))

    return httpx.MockTransport(handler)


def _patch_transport(monkeypatch, transport):
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


def test_transient_failure_is_retried_and_then_succeeds(monkeypatch) -> None:
    counter = {"calls": 0}
    _patch_transport(monkeypatch, _respond(failures=2, counter=counter))

    result = asyncio.run(UserServiceClient._request("GET", "/api/v1/users/me"))

    assert result == {"ok": True}
    assert counter["calls"] == 3, "expected two retries before the successful call"


def test_retries_are_bounded_by_the_policy(monkeypatch) -> None:
    counter = {"calls": 0}
    _patch_transport(monkeypatch, _respond(failures=99, counter=counter))

    with pytest.raises(DependencyUnavailableError):
        asyncio.run(UserServiceClient._request("GET", "/api/v1/users/me"))

    assert counter["calls"] == 3, "retry budget from configs/resilience.yaml is 3 attempts"


def test_repeated_failures_open_the_circuit(monkeypatch) -> None:
    counter = {"calls": 0}
    _patch_transport(monkeypatch, _respond(failures=999, counter=counter))
    breaker = get_circuit_breaker("user-service")

    for _ in range(breaker.failure_threshold):
        with pytest.raises(DependencyUnavailableError):
            asyncio.run(UserServiceClient._request("GET", "/api/v1/users/me"))

    calls_before = counter["calls"]
    with pytest.raises((DependencyUnavailableError, CircuitBreakerOpenError)):
        asyncio.run(UserServiceClient._request("GET", "/api/v1/users/me"))

    assert counter["calls"] == calls_before, "an open circuit must not reach the network"
