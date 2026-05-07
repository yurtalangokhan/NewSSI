"""Web search controller - handles web search and content provider domain logic."""

from __future__ import annotations

import logging
from typing import Any

from controller.base import BaseController
from service.web_search.onyx_web_crawler import OnyxWebCrawler

logger = logging.getLogger(__name__)

_DEFAULT_CONTENT_PROVIDER: dict[str, Any] = {
    "id": 1,
    "name": "Onyx Web Crawler",
    "provider_type": "onyx_web_crawler",
    "is_active": True,
    "config": None,
    "has_api_key": False,
}


class WebSearchController(BaseController):
    """Controller for web search admin configuration endpoints.

    Owns:
    - Search provider listing (currently stub — no external search providers configured)
    - Content provider listing and activation stubs
    - OnyxWebCrawler connectivity test
    - Single-URL crawl with structured result
    """

    def __init__(self) -> None:
        self._crawler = OnyxWebCrawler()

    # =========================================================================
    # Search providers
    # =========================================================================

    def list_search_providers(self) -> list[dict[str, Any]]:
        """Return configured search providers. Currently returns an empty list
        because external search provider persistence is not yet implemented."""
        return []

    # =========================================================================
    # Content providers
    # =========================================================================

    def list_content_providers(self) -> list[dict[str, Any]]:
        """Return active content providers. The built-in Onyx Web Crawler is
        always present; additional providers are not yet persisted."""
        return [_DEFAULT_CONTENT_PROVIDER]

    def activate_content_provider(self, provider_id: int) -> dict[str, Any]:
        return {"status": "ok", "id": provider_id}

    def deactivate_content_provider(self, provider_id: int) -> dict[str, Any]:
        return {"status": "ok", "id": provider_id}

    def reset_default_content_provider(self) -> dict[str, Any]:
        return {"status": "ok"}

    # =========================================================================
    # Crawler operations
    # =========================================================================

    def test_content_provider(self, provider_type: str) -> dict[str, Any]:
        """Run a connectivity test against the requested content provider type.

        Raises HTTPException (400) when the provider type is unsupported or the
        test URL cannot be fetched successfully.
        """
        if provider_type != "onyx_web_crawler":
            self._raise_bad_request(
                f"Unsupported content provider type: {provider_type}"
            )

        try:
            results = self._crawler.contents(["https://example.com"])
            if results and not results[0].scrape_successful:
                self._raise_bad_request(
                    results[0].failure_reason or "Failed to fetch test URL"
                )
        except Exception as exc:
            logger.warning("OnyxWebCrawler test failed: %s", exc)
            self._raise_bad_request(str(exc))

        return {"status": "ok"}

    def crawl_url(self, url: str) -> dict[str, Any]:
        """Crawl *url* with the built-in OnyxWebCrawler and return a structured
        result containing the page title, plain-text content, success flag and
        an optional failure reason.

        Raises HTTPException (422) for obviously malformed URLs and (500) for
        unexpected crawler errors.
        """
        url = url.strip()
        if not url:
            self._raise_bad_request("A non-empty 'url' field is required.")

        if not url.startswith(("http://", "https://")):
            self._raise_bad_request("URL must start with http:// or https://")

        try:
            results = self._crawler.contents([url])
            result = results[0] if results else None
            if result is None:
                self._raise_internal_error("No result returned from crawler.")

            return {
                "title": result.title,
                "content": result.full_content,
                "scrape_successful": result.scrape_successful,
                "failure_reason": result.failure_reason,
            }
        except Exception as exc:
            logger.warning("OnyxWebCrawler crawl failed for %s: %s", url, exc)
            self._raise_internal_error(str(exc))


# Singleton
_web_search_controller: WebSearchController | None = None


def get_web_search_controller() -> WebSearchController:
    """Return the singleton WebSearchController instance."""
    global _web_search_controller
    if _web_search_controller is None:
        _web_search_controller = WebSearchController()
    return _web_search_controller
