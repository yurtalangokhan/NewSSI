from unittest.mock import patch

import pytest

from core.exceptions import BadRequestError
from service.web_search.models import WebContent
from service.web_search.web_search_service import WebSearchService, get_web_search_service


class TestWebSearchService:
    def test_singleton_getter(self):
        c1 = get_web_search_service()
        c2 = get_web_search_service()
        assert c1 is c2
        assert isinstance(c1, WebSearchService)

    def test_list_content_providers(self):
        service = WebSearchService()
        providers = service.list_content_providers()
        assert len(providers) >= 1
        atlas_provider = next(
            (p for p in providers if p["provider_type"] == "atlas_web_crawler"), None
        )
        assert atlas_provider is not None
        assert atlas_provider["name"] == "ATLAS Web Crawler"
        assert atlas_provider["is_active"] is True

    def test_test_content_provider_unsupported(self):
        service = WebSearchService()
        with pytest.raises(BadRequestError) as exc_info:
            service.test_content_provider("unsupported_crawler")
        assert exc_info.value.status_code == 400

    @patch.object(WebSearchService, "__init__", lambda self: None)
    def test_test_content_provider_success(self):
        service = WebSearchService()
        mock_crawler = type("MockCrawler", (), {})()
        mock_crawler.contents = lambda urls: [
            WebContent(
                title="Example",
                link=urls[0],
                full_content="Example page content",
                scrape_successful=True,
            )
        ]
        service._crawler = mock_crawler

        result = service.test_content_provider("atlas_web_crawler")
        assert result == {"status": "ok"}

    @patch.object(WebSearchService, "__init__", lambda self: None)
    def test_crawl_url_success(self):
        service = WebSearchService()
        mock_crawler = type("MockCrawler", (), {})()
        mock_crawler.contents = lambda urls: [
            WebContent(
                title="Crawled Title",
                link=urls[0],
                full_content="Crawled Content with sufficient details",
                scrape_successful=True,
                failure_reason=None,
            )
        ]
        service._crawler = mock_crawler

        result = service.crawl_url("https://example.com/doc")
        assert result["title"] == "Crawled Title"
        assert result["content"] == "Crawled Content with sufficient details"
        assert result["scrape_successful"] is True
        assert result["failure_reason"] is None

    def test_crawl_url_empty_validation(self):
        service = WebSearchService()
        with pytest.raises(BadRequestError) as exc_info:
            service.crawl_url("")
        assert exc_info.value.status_code == 400

    def test_crawl_url_invalid_scheme(self):
        service = WebSearchService()
        with pytest.raises(BadRequestError) as exc_info:
            service.crawl_url("ftp://example.com")
        assert exc_info.value.status_code == 400

    @patch.object(WebSearchService, "__init__", lambda self: None)
    @pytest.mark.asyncio
    async def test_async_crawl_url_success(self):
        service = WebSearchService()
        mock_crawler = type("MockCrawler", (), {})()
        mock_crawler.contents = lambda urls: [
            WebContent(
                title="Async Crawled",
                link=urls[0],
                full_content="Async Content",
                scrape_successful=True,
                failure_reason=None,
            )
        ]
        service._crawler = mock_crawler

        result = await service.async_crawl_url("https://example.com/async")
        assert result["title"] == "Async Crawled"
        assert result["scrape_successful"] is True

    @patch.object(WebSearchService, "__init__", lambda self: None)
    @pytest.mark.asyncio
    async def test_async_test_content_provider(self):
        service = WebSearchService()
        mock_crawler = type("MockCrawler", (), {})()
        mock_crawler.contents = lambda urls: [
            WebContent(
                title="Example",
                link=urls[0],
                full_content="Content",
                scrape_successful=True,
            )
        ]
        service._crawler = mock_crawler

        result = await service.async_test_content_provider("atlas_web_crawler")
        assert result == {"status": "ok"}
