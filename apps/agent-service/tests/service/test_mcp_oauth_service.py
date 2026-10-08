"""Unit tests for MCPOAuthService (plan task 4)."""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _resp(json_body, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_body
    m.text = str(json_body)
    return m


@pytest.fixture(autouse=True)
def _scope_key(monkeypatch):
    from cryptography.fernet import Fernet

    import core.security.encryption as enc

    # config_manager reads the environment on every access; reset_ciphers below
    # drops the cached cipher so the new key takes effect.
    monkeypatch.setenv("MCP_OAUTH_ENCRYPTION_KEY", Fernet.generate_key().decode())
    # Stated rather than defaulted: there is no safe value to guess for
    # where an authorization server delivers codes, so the flow refuses to
    # run without one. See test_mcp_oauth_redirect_base.py.
    monkeypatch.setenv("MCP_OAUTH_REDIRECT_BASE", "https://agenticai.example.com")
    enc.reset_ciphers()
    yield
    enc.reset_ciphers()


def test_pkce_pair_challenge_is_s256_of_verifier():
    from service.mcp.mcp_oauth_service import MCPOAuthService

    verifier, challenge = MCPOAuthService()._pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


@pytest.mark.asyncio
async def test_discover_reads_protected_resource_then_authorization_server(patch_outbound_request):
    from service.mcp.mcp_oauth_service import MCPOAuthService

    prm = {
        "authorization_servers": ["https://as.example"],
        "resource": "https://mcp.example/mcp",
    }
    asm = {
        "authorization_endpoint": "https://as.example/authorize",
        "token_endpoint": "https://as.example/token",
        "registration_endpoint": "https://as.example/register",
        "scopes_supported": ["read", "write"],
    }

    async def fake_get(url, *a, **k):
        if "oauth-protected-resource" in url:
            return _resp(prm)
        if "oauth-authorization-server" in url:
            return _resp(asm)
        return _resp({}, status=404)

    with patch_outbound_request(get=fake_get):
        md = await MCPOAuthService().discover("https://mcp.example/mcp")

    assert md["authorization_endpoint"] == "https://as.example/authorize"
    assert md["token_endpoint"] == "https://as.example/token"
    assert md["registration_endpoint"] == "https://as.example/register"
    assert md["resource"] == "https://mcp.example/mcp"


@pytest.mark.asyncio
async def test_discover_raises_mcpautherror_when_no_metadata(patch_outbound_request):
    from service.mcp.mcp_oauth_service import MCPAuthError, MCPOAuthService

    with patch_outbound_request(get=AsyncMock(return_value=_resp({}, status=404))):
        with pytest.raises(MCPAuthError) as ei:
            await MCPOAuthService().discover("https://mcp.example/mcp")
    assert "discovery failed" in str(ei.value)


@pytest.mark.asyncio
async def test_ensure_client_uses_supplied_credentials_without_dcr():
    from service.mcp.mcp_oauth_service import MCPOAuthService

    with patch("service.mcp.mcp_oauth_service.MCPCredentialService") as cs:
        cs.get_instance.return_value.store_admin_credentials = AsyncMock()
        cid, secret = await MCPOAuthService().ensure_client(
            {"id": "p1"},
            {"registration_endpoint": "https://as/reg"},
            client_id="given-id",
            client_secret="given-secret",
        )
    assert (cid, secret) == ("given-id", "given-secret")


@pytest.mark.asyncio
async def test_ensure_client_performs_dcr_when_no_credentials(patch_outbound_request):
    from service.mcp.mcp_oauth_service import MCPOAuthService

    post = AsyncMock(
        return_value=_resp({"client_id": "dcr-id", "client_secret": "dcr-secret"}, status=201)
    )
    with (
        patch_outbound_request(post=post),
        patch("service.mcp.mcp_oauth_service.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.store_admin_credentials = AsyncMock()
        cid, _secret = await MCPOAuthService().ensure_client(
            {"id": "p1"},
            {"registration_endpoint": "https://as.example/register"},
            client_id=None,
            client_secret=None,
        )
    assert cid == "dcr-id"
    body = post.call_args.kwargs["json"]
    assert body["grant_types"] == ["authorization_code", "refresh_token"]
    assert body["redirect_uris"][0].endswith("/mcp/oauth/callback")


@pytest.mark.asyncio
async def test_ensure_client_raises_without_registration_endpoint():
    from service.mcp.mcp_oauth_service import MCPAuthError, MCPOAuthService

    with pytest.raises(MCPAuthError) as ei:
        await MCPOAuthService().ensure_client({"id": "p1"}, {}, client_id=None, client_secret=None)
    assert "manual client registration" in str(ei.value)


@pytest.mark.asyncio
async def test_begin_builds_authorization_url_and_persists_session():
    from service.mcp.mcp_oauth_service import MCPOAuthService

    svc = MCPOAuthService()
    svc._session_repo = AsyncMock()
    svc._provider_repo = AsyncMock()
    md = {
        "authorization_endpoint": "https://as.example/authorize",
        "token_endpoint": "https://as.example/token",
        "registration_endpoint": None,
        "scopes_supported": ["read"],
        "resource": "https://mcp.example/mcp",
    }
    with (
        patch.object(svc, "discover", AsyncMock(return_value=md)),
        patch.object(svc, "ensure_client", AsyncMock(return_value=("cid", "csec"))),
    ):
        url = await svc.begin(
            {"id": "p1", "url": "https://mcp.example/mcp"},
            user_id="u1",
            return_path="/admin/actions/mcp",
            include_resource_param=True,
            client_id=None,
            client_secret=None,
        )

    assert url.startswith("https://as.example/authorize?")
    assert "code_challenge_method=S256" in url
    assert "resource=https%3A%2F%2Fmcp.example%2Fmcp" in url
    svc._session_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_exchanges_code_and_stores_tokens(patch_outbound_request):
    from service.mcp.mcp_oauth_service import MCPOAuthService

    svc = MCPOAuthService()
    svc._session_repo = AsyncMock()
    svc._session_repo.get.return_value = {
        "state": "st",
        "provider_id": "p1",
        "user_id": "u1",
        "code_verifier": "ver",
        "redirect_uri": "https://app/mcp/oauth/callback",
        "client_id": "cid",
        "client_secret_encrypted": None,
        "token_url": "https://as.example/token",
        "return_path": "/admin/actions/mcp",
    }
    svc._provider_repo = AsyncMock()
    svc._provider_repo.get_by_id.return_value = {
        "id": "p1",
        "name": "GitHub Copilot",
        "auth_performer": "PER_USER",
    }
    post = AsyncMock(
        return_value=_resp(
            {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600, "scope": "read"}
        )
    )
    with (
        patch_outbound_request(post=post),
        patch("service.mcp.mcp_oauth_service.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.store_oauth_tokens = AsyncMock()
        out = await svc.complete("st", "the-code")

    assert out["redirect_url"] == "/admin/actions/mcp"
    assert out["server_name"] == "GitHub Copilot"
    cs.get_instance.return_value.store_oauth_tokens.assert_awaited_once()
    svc._provider_repo.set_status.assert_awaited_with("p1", "CONNECTED")
    svc._session_repo.delete.assert_awaited_with("st")


@pytest.mark.asyncio
async def test_complete_raises_on_missing_session():
    from service.mcp.mcp_oauth_service import MCPAuthError, MCPOAuthService

    svc = MCPOAuthService()
    svc._session_repo = AsyncMock()
    svc._session_repo.get.return_value = None
    with pytest.raises(MCPAuthError) as ei:
        await svc.complete("nope", "c")
    assert "session not found or expired" in str(ei.value)
