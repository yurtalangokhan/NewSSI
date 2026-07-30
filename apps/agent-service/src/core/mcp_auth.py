"""Helpers for authenticating internal MCP client calls."""

from __future__ import annotations

from urllib.parse import urlparse

from core.settings import settings

_INTERNAL_MCP_HOSTS = {
    "localhost",
    "127.0.0.1",
    "host.docker.internal",
    "kong",
    "tools-service",
    "mcp-server",
}


def _configured_internal_urls() -> set[str]:
    return {
        str(url).rstrip("/")
        for url in (
            getattr(settings, "MCP_SERVER_URL", None),
            getattr(settings, "TOOLS_SERVICE_URL", None),
        )
        if url
    }


def _is_internal_mcp_url(url: str) -> bool:
    normalized_url = url.rstrip("/")
    if normalized_url in _configured_internal_urls():
        return True

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = parsed.hostname or ""
    if hostname not in _INTERNAL_MCP_HOSTS:
        return False

    if parsed.path.startswith("/internal/tools-service/mcp"):
        return True

    return (parsed.port in {8002, 8003}) and parsed.path.rstrip("/").endswith("/mcp")


def internal_mcp_headers(url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
    """Return headers for built-in/internal MCP server calls."""
    resolved_headers = dict(headers or {})
    if "Authorization" in resolved_headers or not _is_internal_mcp_url(url):
        return resolved_headers

    token = (settings.INTERNAL_SERVICE_TOKEN or "").strip()
    if token:
        resolved_headers["Authorization"] = f"Bearer {token}"
        resolved_headers["X-Internal-Service-Token"] = token

    return resolved_headers
