from unittest.mock import patch

import pytest
from fastapi import HTTPException

from controller.web_search_controller import WebSearchController, get_web_search_controller
from service.web_search.models import WebContent


class TestWebSearchController:
    def test_singleton_getter(self):
        c1 = get_web_search_controller()
        c2 = get_web_search_controller()
        assert c1 is c2
        assert isinstance(c1, WebSearchController)

    def test_list_content_providers(self):
        controller = WebSearchController()
        providers = controller.list_content_providers()
        assert len(providers) >= 1
        atlas_provider = next(
            (p for p in providers if p["provider_type"] == "atlas_web_crawler"), None
        )
        assert atlas_provider is not None
        assert atlas_provider["name"] == "ATLAS Web Crawler"
        assert atlas_provider["is_active"] is True

    def test_test_content_provider_unsupported(self):
        controller = WebSearchController()
        with pytest.raises(HTTPException) as exc_info:
            controller.test_content_provider("unsupported_crawler")
        assert exc_info.value.status_code == 400

    @patch.object(WebSearchController, "__init__", lambda self: None)
    def test_test_content_provider_success(self):
        controller = WebSearchController()
        mock_crawler = type("MockCrawler", (), {})()
        mock_crawler.contents = lambda urls: [
            WebContent(
                title="Example",
                link=urls[0],
                full_content="Example page content",
                scrape_successful=True,
            )
        ]
        controller._crawler = mock_crawler

        result = controller.test_content_provider("atlas_web_crawler")
        assert result == {"status": "ok"}

    @patch.object(WebSearchController, "__init__", lambda self: None)
    def test_crawl_url_success(self):
        controller = WebSearchController()
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
        controller._crawler = mock_crawler

        result = controller.crawl_url("https://example.com/doc")
        assert result["title"] == "Crawled Title"
        assert result["content"] == "Crawled Content with sufficient details"
        assert result["scrape_successful"] is True
        assert result["failure_reason"] is None

    def test_crawl_url_empty_validation(self):
        controller = WebSearchController()
        with pytest.raises(HTTPException) as exc_info:
            controller.crawl_url("")
        assert exc_info.value.status_code == 400

    def test_crawl_url_invalid_scheme(self):
        controller = WebSearchController()
        with pytest.raises(HTTPException) as exc_info:
            controller.crawl_url("ftp://example.com")
        assert exc_info.value.status_code == 400
