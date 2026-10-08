"""Allow-list for the client-supplied mcp_url field.

A full server-side MCP server registry (named servers, admin-managed
credentials, per-server tool pools) is a separate piece of design work,
deliberately deferred. Until that lands, this module is the whole
defence for the two concrete harms the audit found in
agents/configurable_mcp_agent.py:

1. INTERNAL_SERVICE_TOKEN was attached to whatever host the client named
   in configurable.mcp_url (SSRF + credential exfiltration). A value not
   on this allow-list now silently resolves to the platform's own
   builtin MCP server instead of being used.
2. Because resolve_allowed_mcp_url falls back to the SAME builtin URL
   for every disallowed value, `mcp_url != default_mcp_url()` is false
   for an attacker-supplied URL, so configurable_mcp_agent's three
   "reload if URL changed" call sites never touch the shared
   self._mcp_tools cache on account of a value that isn't legitimately
   configured. A different legitimate server that IS added to
   MCP_URL_ALLOWLIST still reloads that shared cache -- multi-server
   pooling without cross-request bleed is exactly the registry design
   work this module intentionally does not attempt.
"""

from __future__ import annotations

from functools import cache
from urllib.parse import urlparse

from config_manager import env

from core.observability.logger import get_logger

logger = get_logger(__name__)


@cache
def default_mcp_url() -> str:
    configured = env.INTERNAL_TOOLS_SERVICE_URL
    if not configured:
        raise RuntimeError("INTERNAL_TOOLS_SERVICE_URL must be configured")
    return configured


@cache
def _allowed_urls() -> frozenset[str]:
    # Exact-match allow-list, configuration-derived only. No request ever
    # adds an entry.
    extra = env.MCP_URL_ALLOWLIST or ()
    return frozenset({default_mcp_url(), *extra})


def is_allowed_mcp_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return url in _allowed_urls()


def resolve_allowed_mcp_url(candidate: str | None) -> str:
    """Return candidate if it is allow-listed, else the builtin URL.

    Never raises: a caller pointing at a disallowed host silently falls
    back to the platform's own MCP server rather than failing the run,
    matching the pre-existing behaviour when mcp_url was simply absent.
    """
    if candidate and is_allowed_mcp_url(candidate):
        return candidate
    if candidate:
        logger.warning(
            "mcp_url %r is not on the allow-list; falling back to the builtin server",
            candidate,
        )
    return default_mcp_url()
