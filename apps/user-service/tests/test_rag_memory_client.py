"""Tests for the HTTP client that keeps rag-service's memory-facts
semantic index in sync with this service's canonical Postgres fact store.
Uses httpx.MockTransport rather than hitting a real rag-service.
"""

import json

from error_contract import ConfigurationError, DependencyUnavailableError
import httpx
import pytest

from src.client import rag_memory_client


@pytest.fixture(autouse=True)
def _configured_rag_url(monkeypatch):
    # Every test below is about the request this client builds once it has a
    # base URL -- not about resolving one. The tests that are about resolving
    # it override or delete this themselves.
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag-service:8000")


def _ok() -> httpx.Response:
    """rag-service answers every call with the shared success envelope."""
    return httpx.Response(200, json={"statusCode": 200, "message": None, "data": None, "error": None})


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_upsert_fact_posts_to_the_memory_facts_endpoint(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content
        return _ok()

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))

    await rag_memory_client.upsert_fact(
        user_id="user-1", fact_id="fact-1", content="User likes tea"
    )

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/v1/memory/facts")
    assert captured["headers"]["x-user-id"] == "user-1"
    assert json.loads(captured["body"]) == {"fact_id": "fact-1", "content": "User likes tea"}


@pytest.mark.asyncio
async def test_upsert_fact_sends_the_internal_token_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return _ok()

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))

    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "shared-secret")
    await rag_memory_client.upsert_fact(user_id="user-1", fact_id="fact-1", content="x")

    assert captured["headers"]["x-internal-token"] == "shared-secret"


@pytest.mark.asyncio
async def test_upsert_fact_raises_on_a_server_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))

    with pytest.raises(DependencyUnavailableError):
        await rag_memory_client.upsert_fact(user_id="user-1", fact_id="fact-1", content="x")


@pytest.mark.asyncio
async def test_delete_fact_deletes_the_specific_fact_path(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return _ok()

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))

    await rag_memory_client.delete_fact(user_id="user-1", fact_id="fact-1")

    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/api/v1/memory/facts/fact-1")


@pytest.mark.asyncio
async def test_delete_all_facts_deletes_the_collection_path(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return _ok()

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))

    await rag_memory_client.delete_all_facts(user_id="user-1")

    assert captured["method"] == "DELETE"
    assert captured["url"].endswith("/api/v1/memory/facts")


@pytest.mark.asyncio
async def test_base_url_comes_from_the_internal_rag_service_url(monkeypatch):
    """The client reads the same key agent-service uses for this backend and
    builds its request from it, trailing slash stripped by the accessor."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return _ok()

    monkeypatch.setattr(rag_memory_client, "_build_client", lambda: _client_with(handler))
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag-service:9000/")

    await rag_memory_client.delete_all_facts(user_id="user-1")

    assert captured["url"] == "http://rag-service:9000/api/v1/memory/facts"


@pytest.mark.asyncio
async def test_a_call_raises_a_named_error_when_rag_is_not_configured(monkeypatch):
    """This client used to silently default to `http://localhost:8000` --
    unreachable from inside this container -- so every memory-fact sync failed
    with an opaque connection error and no hint why. It must now fail loudly,
    naming the missing setting, the moment a call is attempted.
    """
    monkeypatch.delenv("INTERNAL_RAG_SERVICE_API_URL", raising=False)

    with pytest.raises(ConfigurationError):
        await rag_memory_client.upsert_fact(user_id="user-1", fact_id="fact-1", content="x")


def test_client_timeout_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("RAG_HTTP_TIMEOUT_SECONDS", raising=False)
    client = rag_memory_client._build_client()
    assert client.timeout.read == rag_memory_client.DEFAULT_RAG_HTTP_TIMEOUT_SECONDS


def test_client_timeout_follows_the_environment(monkeypatch):
    monkeypatch.setenv("RAG_HTTP_TIMEOUT_SECONDS", "5.5")
    client = rag_memory_client._build_client()
    assert client.timeout.read == 5.5
