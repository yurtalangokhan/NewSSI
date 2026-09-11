"""The one place that decides how agent-service reaches rag-service.

Before this module the base URL, the bearer-header rule and the HTTP timeout
were re-derived at every call site, and the three copies disagreed about the
fallback: the flow compiler assumed Kong on localhost, ProxyRoute assumed the
container's own host, the resolvers assumed an empty string. These tests pin
the single answer so a fourth opinion cannot appear.
"""

from __future__ import annotations

import pytest

from client.rag_http import (
    DEFAULT_RAG_BASE_URL,
    rag_auth_headers,
    rag_timeout_seconds,
    rag_url,
)


@pytest.fixture(autouse=True)
def _clear_rag_env(monkeypatch):
    for name in (
        "RAG_API_URL",
        "RAG_SERVICE_API_URL",
        "INTERNAL_SERVICE_TOKEN",
        "RAG_HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    from core import env as env_module

    env_module.env._cache.clear()
    yield
    env_module.env._cache.clear()


def test_rag_api_url_wins_over_the_legacy_variable(monkeypatch):
    monkeypatch.setenv("RAG_API_URL", "http://rag.internal:9000")
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://legacy:1111")

    assert rag_url("/graph/search") == "http://rag.internal:9000/api/v1/graph/search"


def test_legacy_variable_is_still_honoured(monkeypatch):
    monkeypatch.setenv("RAG_SERVICE_API_URL", "http://legacy:1111/")

    assert rag_url("/graph/search") == "http://legacy:1111/api/v1/graph/search"


def test_trailing_slash_never_doubles_up(monkeypatch):
    monkeypatch.setenv("RAG_API_URL", "http://rag.internal:9000///")

    assert rag_url("/x") == "http://rag.internal:9000/api/v1/x"


def test_unset_falls_back_to_the_single_documented_default():
    assert rag_url("/x") == f"{DEFAULT_RAG_BASE_URL}/api/v1/x"


def test_callers_token_is_preferred_over_the_service_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "service-tok")

    assert rag_auth_headers("user-tok") == {"Authorization": "Bearer user-tok"}


def test_service_token_is_used_when_the_caller_has_none(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "  service-tok  ")

    assert rag_auth_headers(None) == {"Authorization": "Bearer service-tok"}


def test_no_token_at_all_sends_no_authorization_header():
    assert rag_auth_headers(None) == {}


def test_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv("RAG_HTTP_TIMEOUT_SECONDS", "42.5")

    assert rag_timeout_seconds() == 42.5


def test_timeout_has_a_default():
    assert rag_timeout_seconds() == 15.0
