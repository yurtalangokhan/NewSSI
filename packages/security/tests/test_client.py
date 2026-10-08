"""SecureHTTPClient: redirects are followed manually so every hop is
re-validated, and the body streams under a byte cap. Spec TS-6."""

import httpx
import pytest

from security import SecureHTTPClient, UrlPolicyError


@pytest.fixture(autouse=True)
def allow_public_dns(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["93.184.216.34"]
    )


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fetches_body():
    def handler(request):
        return httpx.Response(200, text="hello")

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        result = await client.fetch("https://example.com/")
        assert result.status_code == 200
        assert result.text == "hello"
        assert result.truncated is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_body_is_capped_at_max_bytes():
    def handler(request):
        return httpx.Response(200, text="x" * 10_000)

    client = SecureHTTPClient(max_bytes=1_000, transport=_transport(handler))
    try:
        result = await client.fetch("https://example.com/")
        assert len(result.text.encode("utf-8")) <= 1_000
        assert result.truncated is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redirect_to_internal_address_is_rejected(monkeypatch):
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        return httpx.Response(200, text="metadata")  # pragma: no cover

    def fake_resolve(host, port):
        return ["169.254.169.254"] if host == "169.254.169.254" else ["93.184.216.34"]

    monkeypatch.setattr("security.url_policy._getaddrinfo_hosts", fake_resolve)

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        with pytest.raises(UrlPolicyError):
            await client.fetch("https://example.com/")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redirect_limit_is_enforced():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://example.com/next"})

    client = SecureHTTPClient(max_redirects=2, transport=_transport(handler))
    try:
        with pytest.raises(UrlPolicyError, match="redirect"):
            await client.fetch("https://example.com/")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_blocked_scheme_never_reaches_the_transport():
    def handler(request):  # pragma: no cover - must not run
        raise AssertionError("transport must not be reached")

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        with pytest.raises(UrlPolicyError):
            await client.fetch("file:///etc/passwd")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_final_url_reflects_the_last_hop():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.com/end"})
        return httpx.Response(200, text="done")

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        result = await client.fetch("https://example.com/start")
        assert result.final_url == "https://example.com/end"
        assert result.text == "done"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_redirect_without_location_header_is_rejected():
    def handler(request):
        return httpx.Response(302)

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        with pytest.raises(UrlPolicyError):
            await client.fetch("https://example.com/")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_aclose_is_idempotent():
    client = SecureHTTPClient(transport=_transport(lambda r: httpx.Response(200)))
    await client.aclose()
    await client.aclose()  # must not raise


@pytest.mark.asyncio
async def test_authorization_header_is_stripped_on_cross_origin_redirect(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts",
        lambda host, port: ["93.184.216.34"] if host == "example.com" else ["1.2.3.4"],
    )
    received: list[httpx.Request] = []

    def handler(request):
        received.append(request)
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "https://attacker.example/"})
        return httpx.Response(200, text="attacker")

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        await client.fetch(
            "https://example.com/",
            headers={"Authorization": "Bearer secret", "X-Other": "kept"},
        )
    finally:
        await client.aclose()

    assert "authorization" not in {h.lower() for h in received[1].headers}
    assert received[1].headers["x-other"] == "kept"
    assert received[0].headers["authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_authorization_header_is_kept_on_same_origin_redirect(monkeypatch):
    monkeypatch.setattr(
        "security.url_policy._getaddrinfo_hosts", lambda host, port: ["93.184.216.34"]
    )
    received: list[httpx.Request] = []

    def handler(request):
        received.append(request)
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://example.com/end"})
        return httpx.Response(200, text="done")

    client = SecureHTTPClient(transport=_transport(handler))
    try:
        await client.fetch(
            "https://example.com/start", headers={"Authorization": "Bearer secret"}
        )
    finally:
        await client.aclose()

    assert received[1].headers["authorization"] == "Bearer secret"
