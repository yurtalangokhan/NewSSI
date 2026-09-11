from __future__ import annotations

import json

from src.core.settings import get_settings
from src.core.trusted import TrustedToolContext
from src.core.trusted_context import set_current_trusted_context
from src.tools.knowledge_tools import database_search_results, graph_search_results


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_database_search_calls_rag_retrieval_with_trusted_context(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, *, json, headers):
            calls["url"] = url
            calls["json"] = json
            calls["headers"] = headers
            return _FakeResponse({"context": "retrieved document context"})

    _set_required_env(monkeypatch)
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://rag-service:8080")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "internal-token")
    monkeypatch.setattr("src.tools.knowledge_tools.httpx.Client", FakeClient)
    set_current_trusted_context(TrustedToolContext(user_id="user-1", tenant_id="tenant-1"))

    try:
        result = database_search_results("pricing policy", ["collection-1"], limit=3)
    finally:
        set_current_trusted_context(None)

    assert result == "retrieved document context"
    assert calls["url"] == "http://rag-service:8080/api/v1/retrieval"
    assert calls["json"] == {
        "query": "pricing policy",
        "collection_id": "collection-1",
        "kind": "vector",
        "limit": 3,
    }
    assert calls["headers"]["x-internal-token"] == "internal-token"
    assert calls["headers"]["x-user-id"] == "user-1"
    assert calls["headers"]["x-tenant-id"] == "tenant-1"


def test_graph_search_combines_multiple_collection_contexts(monkeypatch):
    responses = [
        {"context": "first graph context"},
        {"context": "second graph context"},
    ]

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return _FakeResponse(responses.pop(0))

    _set_required_env(monkeypatch)
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://rag-service:8080/api/v1")
    monkeypatch.setattr("src.tools.knowledge_tools.httpx.Client", FakeClient)
    set_current_trusted_context(TrustedToolContext(user_id="user-1"))

    try:
        result = graph_search_results("roadmap", ["a", "b"])
    finally:
        set_current_trusted_context(None)

    assert result == "first graph context\n\nsecond graph context"


def test_knowledge_search_requires_collection_ids():
    output = json.loads(database_search_results("question", []))

    assert output["success"] is False
    assert output["error_category"] == "validation"


def test_database_search_uses_trusted_collection_binding(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, _url, *, json, headers):
            calls["json"] = json
            calls["headers"] = headers
            return _FakeResponse({"context": "trusted collection context"})

    _set_required_env(monkeypatch)
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://rag-service:8080")
    monkeypatch.setattr("src.tools.knowledge_tools.httpx.Client", FakeClient)
    set_current_trusted_context(
        TrustedToolContext(
            user_id="user-1",
            binding_references={"database_search.collection_ids": '["bound-collection"]'},
        )
    )

    try:
        result = database_search_results("question", collection_ids=None)
    finally:
        set_current_trusted_context(None)

    assert result == "trusted collection context"
    assert calls["json"]["collection_id"] == "bound-collection"
    assert calls["headers"]["x-user-id"] == "user-1"


def _set_required_env(monkeypatch):
    values = {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": "8003",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "tools",
        "POSTGRES_PASSWORD": "tools",
        "POSTGRES_DB": "tools",
        "USER_SERVICE_URL": "http://user-service:8000",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
