"""The MCP OAuth redirect URI must be configured, and must be safe.

The redirect URI is where a remote authorization server sends the
authorization code back. It was built from MCP_OAUTH_REDIRECT_BASE with a
default of http://localhost:3000, so a deployment that never set it did not
fail -- it asked the remote server to deliver codes to whatever happens to
be listening on the *browser's* own localhost:3000, over plain http.

There is no safe default for this, so there is no default: an unset base
fails the flow loudly instead of quietly pointing somewhere else. And the
base must be https unless it is a loopback address, which is the one
exception the OAuth native-app guidance carves out (RFC 8252 s7.3).
"""

from __future__ import annotations

import pytest

from service.mcp.mcp_credential_service import MCPAuthError
from service.mcp.mcp_oauth_service import MCPOAuthService


def _set_base(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("MCP_OAUTH_REDIRECT_BASE", raising=False)
    else:
        monkeypatch.setenv("MCP_OAUTH_REDIRECT_BASE", value)


def test_an_unset_base_fails_the_flow(monkeypatch) -> None:
    _set_base(monkeypatch, None)

    with pytest.raises(MCPAuthError, match="MCP_OAUTH_REDIRECT_BASE"):
        MCPOAuthService._redirect_uri()


def test_a_blank_base_fails_the_flow(monkeypatch) -> None:
    _set_base(monkeypatch, "   ")

    with pytest.raises(MCPAuthError, match="MCP_OAUTH_REDIRECT_BASE"):
        MCPOAuthService._redirect_uri()


def test_an_https_base_is_accepted(monkeypatch) -> None:
    _set_base(monkeypatch, "https://agenticai.example.com")

    assert MCPOAuthService._redirect_uri() == ("https://agenticai.example.com/mcp/oauth/callback")


def test_a_trailing_slash_does_not_double_up(monkeypatch) -> None:
    _set_base(monkeypatch, "https://agenticai.example.com/")

    assert MCPOAuthService._redirect_uri() == ("https://agenticai.example.com/mcp/oauth/callback")


@pytest.mark.parametrize(
    "loopback",
    ["http://localhost:3000", "http://127.0.0.1:3000", "http://[::1]:3000"],
)
def test_plain_http_is_allowed_only_on_loopback(monkeypatch, loopback: str) -> None:
    """The carve-out exists because a loopback redirect never leaves the machine."""
    _set_base(monkeypatch, loopback)

    assert MCPOAuthService._redirect_uri().endswith("/mcp/oauth/callback")


def test_plain_http_to_a_real_host_is_refused(monkeypatch) -> None:
    """An authorization code in cleartext to a routable host is a credential leak."""
    _set_base(monkeypatch, "http://agenticai.example.com")

    with pytest.raises(MCPAuthError, match="https"):
        MCPOAuthService._redirect_uri()
