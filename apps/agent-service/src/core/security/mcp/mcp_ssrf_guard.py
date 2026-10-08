"""SSRF guard for admin-supplied external MCP server URLs.

An enterprise admin is trusted to decide *which external server* to federate
with. That trust does not extend to making agent-service open connections to
its own infrastructure: the boundary being crossed is app->infrastructure,
not user->app. The harm is concrete, because
``MCPCredentialService.resolve_headers`` attaches the stored credentials to
whatever host the provider URL names — so an internal URL is both an SSRF
probe and a credential exfiltration channel.

This module is deliberately separate from :mod:`core.mcp_url_policy`, which
guards a different path (the client-supplied ``configurable.mcp_url``) with an
exact-match allow-list. Here we cannot use an allow-list: the whole point of
the feature is that an admin types an arbitrary URL. So we validate the
*resolved addresses* instead.

Validation runs twice by design: once when the provider is created or updated
(so the admin gets an immediate, explainable rejection) and again when a
connection is actually opened (so a name that later starts resolving to an
internal address — DNS rebinding, or simply a changed record — is still
refused).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from config_manager import env
from error_contract import ApplicationError
from security import (
    UrlPolicyError,
    is_blocked_ip,
    is_metadata_address,
    resolve_addresses_async,
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class MCPUrlRejected(ApplicationError):  # noqa: N818 - name is the API surface; callers catch this exact name
    """An MCP server URL that the platform must not be pointed at.

    Carries the platform error contract so the admin sees the actual reason
    (422) instead of an opaque 500.
    """

    status_code = 422
    code = "mcp_provider.url_rejected"
    message = "The MCP server URL is not allowed."

    def __init__(self, reason: str) -> None:
        super().__init__(message=reason, message_key="errors.security.url_rejected")


def _allow_private_urls() -> bool:
    """Whether this deployment hosts MCP servers on its own network.

    Secure by default. On-prem installs that genuinely run an MCP server at
    an internal address set ``MCP_ALLOW_PRIVATE_URLS=true``; that widens the
    address check but never unblocks the metadata endpoints, which
    :func:`security.is_metadata_address` reports separately for exactly that
    reason.
    """
    return bool(getattr(env, "MCP_ALLOW_PRIVATE_URLS", False))


def _reject_address(raw: str) -> None:
    """Raise if ``raw`` is an address the platform must not connect to."""
    try:
        ipaddress.ip_address(raw)
    except ValueError as exc:
        raise MCPUrlRejected(f"{raw!r} is not a usable IP address") from exc

    if is_metadata_address(raw):
        raise MCPUrlRejected(f"{raw} is a link-local/metadata address and is never allowed")

    if _allow_private_urls():
        return

    if is_blocked_ip(raw):
        raise MCPUrlRejected(
            f"{raw} is not a public address; set MCP_ALLOW_PRIVATE_URLS=true "
            "if this deployment intentionally hosts MCP servers internally"
        )


async def validate_mcp_server_url(url: str | None) -> str:
    """Return ``url`` unchanged if the platform may connect to it.

    Raises :class:`MCPUrlRejected` with an admin-readable reason otherwise.
    """
    if not url or not url.strip():
        raise MCPUrlRejected("server URL is required")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise MCPUrlRejected("server URL must use http or https")

    # Not a URL-policy concern: MCPCredentialService attaches the stored
    # credentials to this URL, so a URL carrying its own is a credential leak.
    if parsed.username or parsed.password:
        raise MCPUrlRejected("server URL must not embed credentials")

    try:
        host = parsed.hostname
    except ValueError as exc:
        raise MCPUrlRejected("server URL host is malformed") from exc
    if not host:
        raise MCPUrlRejected("server URL must include a host")

    # Accessing .port is what validates it: an out-of-range port raises
    # ValueError here rather than at connection time.
    try:
        _ = parsed.port
    except ValueError as exc:
        raise MCPUrlRejected("server URL port is invalid") from exc

    # A literal address is checked directly; only a name needs DNS.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = await resolve_addresses_async(host)
        except UrlPolicyError as exc:
            raise MCPUrlRejected(f"could not resolve host {host!r}") from exc
        for address in addresses:
            _reject_address(address)
    else:
        _reject_address(host)

    return url
