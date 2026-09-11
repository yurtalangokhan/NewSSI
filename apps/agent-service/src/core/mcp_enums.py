"""Canonical enumerations for external MCP providers.

One source of truth for the auth-type / auth-performer / server-status / transport
vocabularies that were previously re-declared as bare string sets in
``models/mcp_admin.py`` and compared against string literals in
``service/MCPCredentialService.py`` and ``service/MCPOAuthService.py``.

All are :class:`enum.StrEnum`, so ``MCPAuthType.OAUTH == "OAUTH"`` and JSON
serialization is unchanged.
"""

from __future__ import annotations

from enum import StrEnum


class MCPAuthType(StrEnum):
    """How a provider authenticates outbound MCP calls."""

    NONE = "NONE"
    API_TOKEN = "API_TOKEN"
    OAUTH = "OAUTH"
    PT_OAUTH = "PT_OAUTH"  # OAuth pass-through (use the caller's token verbatim)


class MCPAuthPerformer(StrEnum):
    """Who owns the credentials — one shared admin identity or each end user."""

    ADMIN = "ADMIN"
    PER_USER = "PER_USER"


class MCPServerStatus(StrEnum):
    """Lifecycle state of a registered MCP server."""

    CREATED = "CREATED"
    AWAITING_AUTH = "AWAITING_AUTH"
    FETCHING_TOOLS = "FETCHING_TOOLS"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class MCPTransport(StrEnum):
    """Wire transport for the MCP session."""

    STREAMABLE_HTTP = "STREAMABLE_HTTP"
    SSE = "SSE"

    @classmethod
    def normalize(cls, value: str | None) -> MCPTransport:
        """Coerce a free-form transport string; default to streamable HTTP."""
        if not value:
            return cls.STREAMABLE_HTTP
        canonical = value.strip().upper().replace("-", "_")
        return cls.SSE if canonical == cls.SSE.value else cls.STREAMABLE_HTTP
