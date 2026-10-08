"""Every outbound HTTP call goes through the shared pooled client.

The behaviour these tests pin:

* a dependency reuses one client instance across calls (that is the whole point
  — a new client per request is a new TCP connection per request);
* an explicit per-request timeout overrides the dependency's policy;
* an open circuit surfaces as the platform's typed 503, not as a
  resilience-package exception;
* `external` addresses never share a breaker with each other.
"""

from __future__ import annotations

from error_contract import DependencyUnavailableError
import httpx
import pytest

from core.http import outbound


def _fake_client(monkeypatch, *, calls: list | None = None) -> httpx.AsyncClient:
    """Install a recording client for a dependency and return it."""

    async def _handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    monkeypatch.setattr(outbound, "get_shared_client", lambda name, **kw: client)
    return client


@pytest.mark.asyncio
async def test_one_client_instance_serves_every_call(monkeypatch) -> None:
    """Two lookups for a dependency must be the *same* client.

    A new client per call is exactly the bug being fixed, so this asserts the
    delegation contract: ``outbound.get_client`` must go through the process
    registry and hand back the instance it already created. The registry is
    faked rather than used for real — a client that outlives the test that made
    it would later be closed from another event loop.
    """
    registry: dict[str, httpx.AsyncClient] = {}
    created: list[str] = []

    def _shared(name: str, **kwargs: object) -> httpx.AsyncClient:
        if name not in registry:
            created.append(name)
            registry[name] = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200))
            )
        return registry[name]

    monkeypatch.setattr(outbound, "get_shared_client", _shared)

    first = outbound.get_client(outbound.RAG_SERVICE)
    second = outbound.get_client(outbound.RAG_SERVICE)

    assert first is second
    assert created == [outbound.RAG_SERVICE]

    await registry[outbound.RAG_SERVICE].aclose()


@pytest.mark.asyncio
async def test_explicit_timeout_overrides_the_dependency_policy(monkeypatch) -> None:
    calls: list[httpx.Request] = []
    client = _fake_client(monkeypatch, calls=calls)

    await outbound.request(outbound.RAG_SERVICE, "GET", "http://rag/health", timeout=3.5)

    assert calls[0].extensions["timeout"]["connect"] == 3.5
    await client.aclose()


@pytest.mark.asyncio
async def test_dependency_policy_supplies_the_timeout_by_default(monkeypatch) -> None:
    calls: list[httpx.Request] = []
    client = _fake_client(monkeypatch, calls=calls)
    monkeypatch.setattr(outbound, "timeout_for", lambda name: 21.0)

    await outbound.request(outbound.RAG_SERVICE, "GET", "http://rag/health")

    assert calls[0].extensions["timeout"]["connect"] == 21.0
    await client.aclose()


def test_one_sync_client_instance_serves_every_call(monkeypatch) -> None:
    """The sync twin has the same contract, for blocking callers.

    ``httpx.get`` / ``httpx.post`` build and discard a client — and a connection
    pool — per call, so a sync caller that looks a dependency up twice must get
    the same instance back.
    """
    registry: dict[str, httpx.Client] = {}
    created: list[str] = []

    def _shared(name: str, **kwargs: object) -> httpx.Client:
        if name not in registry:
            created.append(name)
            registry[name] = httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200))
            )
        return registry[name]

    monkeypatch.setattr(outbound, "get_shared_sync_client", _shared)

    first = outbound.get_sync_client(outbound.EXTERNAL)
    second = outbound.get_sync_client(outbound.EXTERNAL)

    assert first is second
    assert created == [outbound.EXTERNAL]

    registry[outbound.EXTERNAL].close()


def test_resolve_timeout_prefers_the_explicit_value(monkeypatch) -> None:
    monkeypatch.setattr(outbound, "timeout_for", lambda name: 99.0)

    assert outbound.resolve_timeout(outbound.RAG_SERVICE, 2.0) == 2.0
    assert outbound.resolve_timeout(outbound.RAG_SERVICE) == 99.0


@pytest.mark.asyncio
async def test_open_circuit_becomes_the_typed_dependency_error(monkeypatch) -> None:
    from security import CircuitBreakerOpenError

    _fake_client(monkeypatch)

    class _OpenBreaker:
        async def __aenter__(self):
            raise CircuitBreakerOpenError("rag-service", 12.0)

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(outbound, "get_circuit_breaker", lambda name: _OpenBreaker())

    with pytest.raises(outbound.DependencyUnavailableError) as error:
        await outbound.request(outbound.RAG_SERVICE, "GET", "http://rag/health")

    assert error.value.status_code == 503
    assert error.value.code == "rag-service.circuit_open"
    # RFC 7231: the 503 tells the caller when the circuit will be retried.
    assert error.value.headers["Retry-After"] == "12"


@pytest.mark.asyncio
async def test_external_dependency_skips_the_shared_breaker(monkeypatch) -> None:
    _fake_client(monkeypatch)

    def _must_not_be_called(name: str):
        raise AssertionError("external calls must not use the shared breaker")

    monkeypatch.setattr(outbound, "get_circuit_breaker", _must_not_be_called)

    response = await outbound.request(outbound.EXTERNAL, "GET", "http://example.test")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_request_json_raises_for_error_status(monkeypatch) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500, json={"detail": "nope"}))
    )
    monkeypatch.setattr(outbound, "get_shared_client", lambda name, **kw: client)

    with pytest.raises(DependencyUnavailableError):
        await outbound.request_json(outbound.RAG_SERVICE, "GET", "http://rag/health")

    await client.aclose()


def test_every_named_dependency_has_a_policy_entry() -> None:
    """A dependency named in code must be configurable in resilience.yaml.

    Otherwise its timeout/retry/breaker silently come from `defaults`, which is
    how a service ends up with a 15s budget nobody chose.
    """
    from security import load_resilience_config

    config = load_resilience_config()
    configured = set((config.get("dependencies") or {}).keys())

    named = {
        outbound.USER_SERVICE,
        outbound.RAG_SERVICE,
        outbound.RAG_SERVICE_INGEST,
        outbound.TOOLS_SERVICE,
        outbound.KEYCLOAK,
        outbound.OLLAMA,
        outbound.VLLM,
    }

    assert named <= configured, sorted(named - configured)


def test_the_ingest_dependency_has_a_long_budget_and_sends_once() -> None:
    """rag-service embeds a whole batch inside the request: minutes, not the
    15 s chat budget. The sync runner retries a batch under its idempotency key,
    so the transport must not add retries of its own (each one re-posts the
    batch and waits on the idempotency lock)."""
    from security import load_resilience_config, timeout_for

    assert timeout_for(outbound.RAG_SERVICE_INGEST) >= 300
    assert timeout_for(outbound.RAG_SERVICE_INGEST) > timeout_for(outbound.RAG_SERVICE)
    policy = load_resilience_config()["dependencies"][outbound.RAG_SERVICE_INGEST]
    assert policy["retry"]["maxAttempts"] == 1
