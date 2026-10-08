"""Allow-list for configurable.mcp_url. Spec C3/T2 (reduced scope: a full
MCP server registry is deferred; this closes the SSRF/token-leak and the
shared-tool-pool-poisoning harms without it)."""

import pytest

from core.security.mcp import mcp_url_policy
from core.security.mcp.mcp_url_policy import (
    default_mcp_url,
    is_allowed_mcp_url,
    resolve_allowed_mcp_url,
)


@pytest.fixture(autouse=True)
def clear_caches(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_SERVICE_URL", "http://tools-service:8003/mcp")
    monkeypatch.delenv("INTERNAL_MCP_SERVER_URL", raising=False)
    default_mcp_url.cache_clear()
    mcp_url_policy._allowed_urls.cache_clear()
    yield
    default_mcp_url.cache_clear()
    mcp_url_policy._allowed_urls.cache_clear()


def test_builtin_url_is_allowed():
    assert is_allowed_mcp_url(default_mcp_url()) is True


def test_legacy_internal_tools_key_is_ignored(monkeypatch):
    monkeypatch.setenv("INTERNAL_MCP_SERVER_URL", "http://legacy-tools:8003/mcp")

    assert default_mcp_url() == "http://tools-service:8003/mcp"


def test_missing_internal_tools_url_fails_clearly(monkeypatch):
    monkeypatch.delenv("INTERNAL_TOOLS_SERVICE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_MCP_SERVER_URL", raising=False)

    with pytest.raises(RuntimeError, match="INTERNAL_TOOLS_SERVICE_URL"):
        default_mcp_url()


@pytest.mark.parametrize(
    "url",
    [
        "http://attacker.example/mcp",
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8003/mcp",
        "https://tools-service.evil.example:8003/mcp",
        None,
        "",
    ],
)
def test_non_allowlisted_url_is_rejected(url):
    assert is_allowed_mcp_url(url) is False


def test_resolve_returns_the_candidate_when_allowlisted():
    url = default_mcp_url()
    assert resolve_allowed_mcp_url(url) == url


def test_resolve_falls_back_to_builtin_for_a_disallowed_url(caplog):
    with caplog.at_level("WARNING"):
        resolved = resolve_allowed_mcp_url("http://attacker.example/mcp")
    assert resolved == default_mcp_url()
    assert "not on the allow-list" in caplog.text


def test_resolve_falls_back_to_builtin_when_no_url_given():
    assert resolve_allowed_mcp_url(None) == default_mcp_url()


def test_allowlist_uses_builtin_when_optional_key_is_absent(monkeypatch):
    monkeypatch.delenv("MCP_URL_ALLOWLIST", raising=False)
    mcp_url_policy._allowed_urls.cache_clear()
    assert mcp_url_policy.env.MCP_URL_ALLOWLIST is None
    assert mcp_url_policy._allowed_urls() == frozenset({default_mcp_url()})
