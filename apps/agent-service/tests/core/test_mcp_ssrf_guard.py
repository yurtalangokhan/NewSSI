"""An admin-supplied MCP server URL must not be able to point the platform at
its own infrastructure.

The boundary crossed here is app->infrastructure, not user->app: the admin is
trusted to choose which *external* server to federate with, but nothing about
that trust implies they may make agent-service open a connection to the cloud
metadata endpoint or an internal service — especially since
MCPCredentialService.resolve_headers attaches the stored credentials to
whatever host the URL names.
"""

import pytest

from security import UrlPolicyError
from core.security.mcp.mcp_ssrf_guard import MCPUrlRejected, validate_mcp_server_url


def _resolves_to(monkeypatch, mapping: dict[str, list[str]]) -> None:
    """Pin DNS so tests never depend on the network.

    Patches the shared resolver rather than a service-local one: the guard
    delegates resolution to ``security.url_policy`` and only owns the policy
    (metadata is never allowed, ``MCP_ALLOW_PRIVATE_URLS`` widens the rest).
    """

    async def fake_resolve(host: str, port: int | None = None) -> list[str]:
        try:
            return mapping[host]
        except KeyError:
            raise UrlPolicyError(f"Could not resolve {host!r}") from None

    monkeypatch.setattr(
        "core.security.mcp.mcp_ssrf_guard.resolve_addresses_async", fake_resolve
    )


@pytest.mark.asyncio
async def test_public_https_url_is_accepted(monkeypatch):
    _resolves_to(monkeypatch, {"mcp.example.com": ["93.184.216.34"]})

    assert (
        await validate_mcp_server_url("https://mcp.example.com/mcp")
        == "https://mcp.example.com/mcp"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host", "address"),
    [
        ("metadata.attacker.test", "169.254.169.254"),  # cloud metadata
        ("internal.attacker.test", "10.1.2.3"),  # private RFC1918
        ("lan.attacker.test", "192.168.1.10"),
        ("cgnat.attacker.test", "100.64.0.1"),  # RFC6598 carrier-grade NAT
        ("loopback.attacker.test", "127.0.0.1"),
        ("unspecified.attacker.test", "0.0.0.0"),
        ("v6loopback.attacker.test", "::1"),
        ("v6ula.attacker.test", "fd00::1"),
        ("v6linklocal.attacker.test", "fe80::1"),
    ],
)
async def test_urls_resolving_to_non_public_addresses_are_rejected(
    monkeypatch, host: str, address: str
):
    _resolves_to(monkeypatch, {host: [address]})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url(f"https://{host}/mcp")


@pytest.mark.asyncio
async def test_ipv4_mapped_ipv6_loopback_is_rejected(monkeypatch):
    """``::ffff:127.0.0.1`` is loopback wearing an IPv6 costume."""
    _resolves_to(monkeypatch, {"mapped.attacker.test": ["::ffff:127.0.0.1"]})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("https://mapped.attacker.test/mcp")


@pytest.mark.asyncio
async def test_every_resolved_address_must_be_public(monkeypatch):
    """A host that resolves to one public and one internal address is rejected.

    Which record the HTTP client picks is not ours to control, so a single
    bad answer poisons the whole name.
    """
    _resolves_to(monkeypatch, {"split.attacker.test": ["93.184.216.34", "10.0.0.5"]})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("https://split.attacker.test/mcp")


@pytest.mark.asyncio
async def test_literal_internal_ip_is_rejected_without_dns(monkeypatch):
    _resolves_to(monkeypatch, {})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/",
        "not-a-url",
        "",
        "https://",
    ],
)
async def test_non_http_schemes_and_malformed_urls_are_rejected(monkeypatch, url: str):
    _resolves_to(monkeypatch, {})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url(url)


@pytest.mark.asyncio
async def test_embedded_credentials_are_rejected(monkeypatch):
    """Userinfo in the URL smuggles an identity past the stored-credential model."""
    _resolves_to(monkeypatch, {"mcp.example.com": ["93.184.216.34"]})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("https://user:pass@mcp.example.com/mcp")


@pytest.mark.asyncio
async def test_unresolvable_host_is_rejected(monkeypatch):
    """Fail closed: a name we cannot check is a name we cannot clear."""
    _resolves_to(monkeypatch, {})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("https://nonexistent.invalid/mcp")


@pytest.mark.asyncio
async def test_private_urls_are_allowed_when_the_deployment_opts_in(monkeypatch):
    """On-prem deployments legitimately host MCP servers on the internal network."""
    monkeypatch.setattr("core.security.mcp.mcp_ssrf_guard._allow_private_urls", lambda: True)
    _resolves_to(monkeypatch, {"mcp.internal.corp": ["10.1.2.3"]})

    assert (
        await validate_mcp_server_url("https://mcp.internal.corp/mcp")
        == "https://mcp.internal.corp/mcp"
    )


@pytest.mark.asyncio
async def test_cloud_metadata_stays_blocked_even_when_private_urls_are_allowed(monkeypatch):
    """Opting into private networking is not opting into credential theft."""
    monkeypatch.setattr("core.security.mcp.mcp_ssrf_guard._allow_private_urls", lambda: True)
    _resolves_to(monkeypatch, {"metadata.attacker.test": ["169.254.169.254"]})

    with pytest.raises(MCPUrlRejected):
        await validate_mcp_server_url("https://metadata.attacker.test/mcp")


def test_rejection_reaches_the_admin_as_a_422_not_a_500():
    """The guard rides the platform error contract, so app.py's registered
    ApplicationError handler renders the actual reason instead of an opaque
    internal error."""
    from error_contract import ApplicationError

    exc = MCPUrlRejected("10.0.0.5 is not a public address")

    assert isinstance(exc, ApplicationError)
    assert exc.status_code == 422
    assert exc.code == "mcp_provider.url_rejected"
    assert "not a public address" in exc.message


class _FakeRepo:
    """Records writes so the tests can assert nothing reached the database."""

    def __init__(self, existing: dict | None = None):
        self.existing = existing
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "p1", **kwargs}

    async def update(self, provider_id, **fields):
        self.updated.append((provider_id, fields))
        return {"id": provider_id, **fields}

    async def get_by_id(self, provider_id):
        return self.existing


def _service(repo: _FakeRepo):
    from service.mcp.mcp_provider_service import MCPProviderService

    service = MCPProviderService.__new__(MCPProviderService)
    service._repo = repo
    return service


@pytest.mark.asyncio
async def test_creating_a_provider_with_an_internal_url_is_refused(monkeypatch):
    """The service, not the route, is the choke point: three routers write
    providers, so guarding only the admin route would leave the others open."""
    _resolves_to(monkeypatch, {})
    repo = _FakeRepo()

    with pytest.raises(MCPUrlRejected):
        await _service(repo).create_provider(name="evil", url="http://169.254.169.254/mcp")

    assert repo.created == []


@pytest.mark.asyncio
async def test_updating_a_provider_url_to_an_internal_address_is_refused(monkeypatch):
    _resolves_to(monkeypatch, {})
    repo = _FakeRepo(existing={"id": "p1", "is_builtin": False, "type": "external"})

    with pytest.raises(MCPUrlRejected):
        await _service(repo).update_provider("p1", url="http://10.0.0.5/mcp")

    assert repo.updated == []


@pytest.mark.asyncio
async def test_updates_that_do_not_touch_the_url_skip_the_guard(monkeypatch):
    _resolves_to(monkeypatch, {})
    repo = _FakeRepo(existing={"id": "p1", "is_builtin": False, "type": "external"})

    await _service(repo).update_provider("p1", description="renamed")

    assert repo.updated == [("p1", {"description": "renamed"})]


@pytest.mark.asyncio
async def test_the_builtin_provider_keeps_its_internal_url(monkeypatch):
    """The platform's own tools-service is internal by definition."""
    _resolves_to(monkeypatch, {})
    repo = _FakeRepo(existing={"id": "p1", "is_builtin": True, "type": "builtin"})

    await _service(repo).update_provider("p1", url="http://localhost:8003/mcp")

    assert repo.updated == [("p1", {"url": "http://localhost:8003/mcp"})]
