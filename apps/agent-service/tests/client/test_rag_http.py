"""The one place that decides how agent-service reaches rag-service.

Before this module the base URL, the bearer-header rule and the HTTP timeout
were re-derived at every call site, and the three copies disagreed about the
fallback: the flow compiler assumed the gateway on localhost, proxy_route assumed the
container's own host, the resolvers assumed an empty string. These tests pin
the single answer so a fourth opinion cannot appear.
"""

from __future__ import annotations

import pytest

from core.http.rag_http import (
    rag_auth_headers,
    rag_base_url,
    rag_timeout_seconds,
    rag_url,
)


@pytest.fixture(autouse=True)
def _clear_rag_env(monkeypatch):
    for name in (
        "INTERNAL_RAG_API_URL",
        "INTERNAL_RAG_SERVICE_API_URL",
        "RAG_API_URL",
        "RAG_SERVICE_API_URL",
        "INTERNAL_SERVICE_TOKEN",
        "RAG_HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_canonical_internal_rag_url_is_used(monkeypatch):
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag.internal:9000")
    monkeypatch.setenv("INTERNAL_RAG_API_URL", "http://legacy:1111")

    assert rag_url("/graph/search") == "http://rag.internal:9000/api/v1/graph/search"


def test_legacy_variable_is_ignored(monkeypatch):
    monkeypatch.setenv("INTERNAL_RAG_API_URL", "http://legacy:1111/")

    with pytest.raises(RuntimeError, match="INTERNAL_RAG_SERVICE_API_URL"):
        rag_base_url()


def test_trailing_slash_never_doubles_up(monkeypatch):
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag.internal:9000///")

    assert rag_url("/x") == "http://rag.internal:9000/api/v1/x"


def test_public_rag_urls_are_ignored(monkeypatch):
    monkeypatch.setenv("RAG_API_URL", "https://public-rag.example")
    monkeypatch.setenv("RAG_SERVICE_API_URL", "https://public-legacy-rag.example")

    with pytest.raises(RuntimeError, match="INTERNAL_RAG_SERVICE_API_URL"):
        rag_base_url()


def test_unset_internal_rag_url_fails_clearly():
    with pytest.raises(RuntimeError, match="INTERNAL_RAG_SERVICE_API_URL"):
        rag_base_url()


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
