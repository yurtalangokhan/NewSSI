"""Web crawl service for single and batch URL crawling."""

from __future__ import annotations

from typing import Any

from core.observability.logger import get_logger
from service.web_search.atlas_web_crawler import AtlasWebCrawler

logger = get_logger(__name__)

_WEB_URL_SCHEMES = ("http://", "https://")


def _has_web_scheme(url: str) -> bool:
    return url.startswith(_WEB_URL_SCHEMES)


class WebCrawlService:
    def __init__(self, crawler: AtlasWebCrawler | None = None) -> None:
        self._crawler = crawler or AtlasWebCrawler()

    def crawl_url(self, url: str) -> dict[str, Any]:
        url = url.strip()
        if not url or not _has_web_scheme(url):
            return {
                "title": "",
                "content": "",
                "scrape_successful": False,
                "failure_reason": "Invalid URL scheme or empty URL",
            }
        try:
            results = self._crawler.contents([url])
            result = results[0] if results else None
            if result is None:
                return {
                    "title": "",
                    "content": "",
                    "scrape_successful": False,
                    "failure_reason": "No crawler result",
                }
            return {
                "title": result.title,
                "content": result.full_content,
                "scrape_successful": result.scrape_successful,
                "failure_reason": result.failure_reason,
            }
        except Exception as exc:
            logger.warning("AtlasWebCrawler crawl failed for %s: %s", url, exc)
            return {
                "title": "",
                "content": "",
                "scrape_successful": False,
                "failure_reason": str(exc),
            }

    def crawl_urls(self, urls: list[str]) -> list[dict[str, Any]]:
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
            logger.warning("AtlasWebCrawler batch crawl failed", exc_info=True)
            return []


_web_crawl_service: WebCrawlService | None = None


def get_web_crawl_service() -> WebCrawlService:
    global _web_crawl_service
    if _web_crawl_service is None:
        _web_crawl_service = WebCrawlService()
    return _web_crawl_service
