"""Web search service - handles web search and content provider domain logic."""

from __future__ import annotations

import asyncio
from typing import Any

from error_contract import ApplicationError, BadRequestError
from error_contract.domain import SSRFBlockedException

from core.observability.logger import get_logger
from service.common.base import BaseService
from service.web_search.atlas_web_crawler import AtlasWebCrawler
from service.web_search.providers import (
    list_content_providers as _svc_list_content_providers,
    list_search_providers as _svc_list_search_providers,
)

logger = get_logger(__name__)

_WEB_URL_SCHEMES = ("http://", "https://")


def _has_web_scheme(url: str) -> bool:
    return url.startswith(_WEB_URL_SCHEMES)


class WebSearchService(BaseService):
    """Service for web search admin configuration endpoints.

    Owns:
    - Search provider listing (currently stub — no external search providers configured)
    - Content provider listing and activation stubs
    - AtlasWebCrawler connectivity test
    - Single-URL crawl with structured result
    """

    def __init__(self) -> None:
        self._crawler = AtlasWebCrawler()

    # =========================================================================
    # Search providers
    # =========================================================================

    def list_search_providers(self) -> list[dict[str, Any]]:
        """Return configured search providers. Currently returns an empty list
        because external search provider persistence is not yet implemented."""
        return _svc_list_search_providers()

    # =========================================================================
    # Content providers
    # =========================================================================

    def list_content_providers(self) -> list[dict[str, Any]]:
        """Return active content providers. The built-in ATLAS Web Crawler is
        always present; additional providers are not yet persisted."""
        return _svc_list_content_providers()

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

        Raises ``BadRequestError`` when the provider type is unsupported or the
        test URL cannot be fetched successfully.
        """
        if provider_type != "atlas_web_crawler":
            raise BadRequestError(
                message_key="errors.web_search.unsupported_provider_type",
                message_params={"provider_type": provider_type},
            )

        try:
            results = self._crawler.contents(["https://example.com"])
            if results and not results[0].scrape_successful:
                raise BadRequestError(message_key="errors.web_search.test_fetch_failed")
        except (SSRFBlockedException, ValueError) as error:
            logger.warning("Crawler test rejected an invalid outbound URL", exc_info=True)
            raise BadRequestError(message_key="errors.web_search.test_fetch_failed") from error

        return {"status": "ok"}

    def crawl_url(self, url: str) -> dict[str, Any]:
        """Crawl *url* with the built-in AtlasWebCrawler and return a structured
        result containing the page title, plain-text content, success flag and
        an optional failure reason.

        Raises ``BadRequestError`` for an empty URL or one without a web
        scheme, and a 500 ``ApplicationError`` for unexpected crawler errors.
        """
        if not isinstance(url, str):
            raise BadRequestError(message_key="errors.web_search.url_invalid_scheme")
        url = url.strip()
        if not url:
            raise BadRequestError(message_key="errors.web_search.url_required")

        if not _has_web_scheme(url):
            raise BadRequestError(message_key="errors.web_search.url_invalid_scheme")

        try:
            results = self._crawler.contents([url])
            result = results[0] if results else None
            if result is None:
                raise ApplicationError(message_key="errors.web_search.no_crawler_result")

            return {
                "title": result.title,
                "content": result.full_content,
                "scrape_successful": result.scrape_successful,
                "failure_reason": result.failure_reason,
            }
        except (SSRFBlockedException, ValueError) as error:
            logger.warning("Crawler rejected invalid URL %s", url, exc_info=True)
            raise BadRequestError(message_key="errors.web_search.url_invalid_scheme") from error

    def crawl_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        """Crawl multiple URLs in a single batch pass with AtlasWebCrawler."""
        clean_urls = [u.strip() for u in urls if u and _has_web_scheme(u.strip())]
        if not clean_urls:
            return []
        try:
            results = self._crawler.contents(clean_urls)
            return [
                {
                    "url": r.url if hasattr(r, "url") else (clean_urls[i] if i < len(clean_urls) else ""),
                    "title": r.title,
                    "content": r.full_content,
                    "scrape_successful": r.scrape_successful,
                    "failure_reason": r.failure_reason,
                }
                for i, r in enumerate(results)
            ]
        except Exception:
            # Batch crawl degrades to an empty result set rather than failing the
            # whole request; per-URL failures already surface as
            # scrape_successful=False entries above.
            logger.warning("AtlasWebCrawler batch crawl failed", exc_info=True)
            return []

    async def async_test_content_provider(self, provider_type: str) -> dict[str, Any]:
        """Asynchronously run a connectivity test, offloading blocking I/O to a thread."""
        return await asyncio.to_thread(self.test_content_provider, provider_type)

    async def async_crawl_url(self, url: str) -> dict[str, Any]:
        """Asynchronously crawl a single URL, offloading blocking I/O to a thread."""
        return await asyncio.to_thread(self.crawl_url, url)

    async def async_crawl_urls(self, urls: list[str]) -> list[dict[str, Any]]:
        """Asynchronously crawl multiple URLs, offloading blocking I/O to a thread."""
        return await asyncio.to_thread(self.crawl_urls, urls)


# Singleton
_web_search_service: WebSearchService | None = None


def get_web_search_service() -> WebSearchService:
    """Return the singleton WebSearchService instance."""
    global _web_search_service
    if _web_search_service is None:
        _web_search_service = WebSearchService()
    return _web_search_service
