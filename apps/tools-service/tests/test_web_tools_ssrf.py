"""fetch_webpage must refuse internal/private targets and must not run a
catastrophic-backtracking regex chain over untrusted HTML. Spec TS-6."""

import pytest
from security import GuardedResponse

from src.tools import web_tools
from src.tools.web_tools import fetch_webpage_content


@pytest.fixture(autouse=True)
def reset_client():
    yield
    web_tools.get_http_client.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:6379/",
        "http://10.0.0.5/admin",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
@pytest.mark.asyncio
async def test_internal_or_disallowed_targets_are_refused(url, monkeypatch):
    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", lambda host, port: ["10.0.0.5"])
    result = await fetch_webpage_content(url)
    assert "not allowed" in result.lower() or "izin" in result.lower()


@pytest.mark.asyncio
async def test_public_target_is_fetched_and_cleaned(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["93.184.216.34"]
    )

    class _Stub:
        async def fetch(self, url, headers=None):
            html = "<html><head><title>Example</title></head><body><p>hello</p></body></html>"
            return GuardedResponse(200, html, url, False)

        async def aclose(self):
            pass

    monkeypatch.setattr(web_tools, "get_http_client", lambda: _Stub())
    out = await fetch_webpage_content("https://example.com/")
    assert "TITLE: Example" in out
    assert "hello" in out


@pytest.mark.asyncio
async def test_html_is_stripped_without_catastrophic_regex(monkeypatch):
    # A pathological input that a `.*?` + DOTALL chain walks quadratically.
    # With a real parser this must complete promptly regardless of size.
    payload = "<script>" + ("<" * 50_000) + "</script><p>readable text</p>"

    class _Stub:
        async def fetch(self, url, headers=None):
            return GuardedResponse(200, payload, url, False)

        async def aclose(self):
            pass

    monkeypatch.setattr(web_tools, "get_http_client", lambda: _Stub())
    out = await fetch_webpage_content("https://example.com/")
    assert "readable text" in out
    assert "<script>" not in out


@pytest.mark.asyncio
async def test_upstream_error_status_is_reported_without_a_raw_exception(monkeypatch):
    class _Stub:
        async def fetch(self, url, headers=None):
            return GuardedResponse(500, "", url, False)

        async def aclose(self):
            pass

    monkeypatch.setattr(web_tools, "get_http_client", lambda: _Stub())
    out = await fetch_webpage_content("https://example.com/")
    assert "500" in out or "could not" in out.lower() or "error" in out.lower()


def test_get_http_client_is_a_singleton():
    a = web_tools.get_http_client()
    b = web_tools.get_http_client()
    assert a is b
