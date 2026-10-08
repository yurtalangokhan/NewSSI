"""Web search provider catalog and defaults.

Web search and content providers catalog and configuration.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_CONTENT_PROVIDER: dict[str, Any] = {
    "id": 1,
    "name": "ATLAS Web Crawler",
    "provider_type": "atlas_web_crawler",
    "is_active": True,
    "description": "Extract text and metadata directly from web pages using headless browser crawling.",
}


def list_search_providers() -> list[dict[str, Any]]:
    """Return configured search providers."""
    return []


def list_content_providers() -> list[dict[str, Any]]:
    """Return active content providers."""
    return [_DEFAULT_CONTENT_PROVIDER]
