from unittest.mock import patch

import requests

from models.web_search import RenderedPage
from service.web_search import AtlasWebCrawler, FailureReason, OnyxWebCrawler
from service.web_search.onyx_web_crawler import _calculate_retry_delay, _parse_retry_after
from service.web_search.url import DNSResolutionError, SSRFBlockedException


def _sample_html() -> bytes:
    body = (
        "<p>"
        + "This is a detailed test article content that contains enough text to satisfy the minimum direct text length requirements for standard crawler extraction without triggering low information fallback. "
        * 3
        + "</p>"
    )
    return f"<html><head><title>Test Page</title></head><body><h1>Hello World</h1>{body}</body></html>".encode()


def _mock_response(
    status_code: int = 200,
    content: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = content if content is not None else _sample_html()
    resp.headers.update(headers or {"Content-Type": "text/html; charset=utf-8"})
    return resp


class TestAtlasWebCrawlerRetry:
    def test_atlas_web_crawler_alias_and_initialization(self):
        assert AtlasWebCrawler is OnyxWebCrawler
        crawler = AtlasWebCrawler(
            max_retries=5,
            retry_backoff_factor=1.0,
            retry_status_codes=(500, 502, 503),
        )
        assert crawler.max_retries == 5
        assert crawler.retry_backoff_factor == 1.0
        assert crawler.retry_status_codes == {500, 502, 503}

    @patch("service.web_search.onyx_web_crawler.OnyxWebCrawler._fetch_via_playwright")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_playwright_fallback_is_disabled_by_default(self, mock_get, mock_fetch_via_playwright):
        mock_get.return_value = _mock_response(status_code=403)

        crawler = AtlasWebCrawler(max_retries=0)
        result = crawler.contents(["https://example.com/protected"])[0]

        assert result.scrape_successful is False
        assert result.failure_reason == FailureReason.HTTP_403_BLOCKED
        mock_fetch_via_playwright.assert_not_called()

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_connection_error_and_recover(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.ConnectionError("Remote disconnected"),
            _mock_response(status_code=200),
        ]

        crawler = AtlasWebCrawler(max_retries=3, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert result.title == "Test Page"
        assert "detailed test article content" in result.full_content
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_timeout_and_recover(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.ConnectTimeout("Connection timed out"),
            _mock_response(status_code=200),
        ]

        crawler = AtlasWebCrawler(max_retries=2, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert result.title == "Test Page"
        assert "detailed test article content" in result.full_content
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_chunked_encoding_error_and_recover(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead"),
            _mock_response(status_code=200),
        ]

        crawler = AtlasWebCrawler(max_retries=2, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert result.title == "Test Page"
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_5xx_status_codes_and_recover(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            _mock_response(status_code=503),
            _mock_response(status_code=502),
            _mock_response(status_code=200),
        ]

        crawler = AtlasWebCrawler(max_retries=3, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert result.title == "Test Page"
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_429_too_many_requests_with_retry_after(self, mock_get, mock_sleep):
        resp_429 = _mock_response(status_code=429, headers={"Retry-After": "2"})
        resp_200 = _mock_response(status_code=200)
        mock_get.side_effect = [resp_429, resp_200]

        crawler = AtlasWebCrawler(max_retries=2, retry_backoff_factor=0.5, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(2.0)

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_retry_on_transient_dns_error(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            DNSResolutionError(
                "Could not resolve hostname 'example.com': Temporary failure in name resolution"
            ),
            _mock_response(status_code=200),
        ]

        crawler = AtlasWebCrawler(max_retries=2, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is True
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_exhaust_all_retries_on_connection_error(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        crawler = AtlasWebCrawler(max_retries=3, retry_backoff_factor=0.01, retry_jitter=False)
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is False
        assert result.failure_reason == FailureReason.NETWORK_ERROR
        assert mock_get.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_exhaust_all_retries_on_503(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response(status_code=503)

        crawler = AtlasWebCrawler(
            max_retries=2,
            retry_backoff_factor=0.01,
            retry_jitter=False,
            playwright_fallback_enabled=False,
        )
        result = crawler.contents(["https://example.com/test"])[0]

        assert result.scrape_successful is False
        assert result.failure_reason == FailureReason.http_status(503)
        assert mock_get.call_count == 3  # 1 initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_non_retriable_404_not_found_fails_immediately(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response(status_code=404)

        crawler = AtlasWebCrawler(max_retries=3, playwright_fallback_enabled=False)
        result = crawler.contents(["https://example.com/not-found"])[0]

        assert result.scrape_successful is False
        assert result.failure_reason == FailureReason.http_status(404)
        assert mock_get.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_non_retriable_ssrf_blocked_fails_immediately(self, mock_get, mock_sleep):
        mock_get.side_effect = SSRFBlockedException("Access to internal IP address is not allowed")

        crawler = AtlasWebCrawler(max_retries=3)
        result = crawler.contents(["http://192.168.1.1/admin"])[0]

        assert result.scrape_successful is False
        assert result.failure_reason == FailureReason.SSRF_BLOCKED
        assert mock_get.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("service.web_search.onyx_web_crawler.time.sleep")
    @patch("service.web_search.onyx_web_crawler.fetch_rendered_html")
    @patch("service.web_search.onyx_web_crawler.ssrf_safe_get")
    def test_playwright_fallback_retry(self, mock_get, mock_pw, mock_sleep):
        # 403 triggers Playwright fallback
        mock_get.return_value = _mock_response(status_code=403)
        # Playwright fails first time (e.g. transient timeout), succeeds second time
        mock_pw.side_effect = [
            None,
            RenderedPage(
                html="<html><head><title>Rendered</title></head><body><p>"
                + "Rendered full content for test extraction paragraph with sufficient text. " * 3
                + "</p></body></html>",
                final_url="https://example.com/pw-test",
            ),
        ]

        crawler = AtlasWebCrawler(
            max_retries=0, playwright_max_retries=1, playwright_fallback_enabled=True
        )
        result = crawler.contents(["https://example.com/pw-test"])[0]

        assert result.scrape_successful is True
        assert result.title == "Rendered"
        assert mock_pw.call_count == 2
        assert mock_sleep.call_count == 1


class TestRetryHelpers:
    def test_parse_retry_after_integer(self):
        assert _parse_retry_after("5", max_delay=10.0) == 5.0
        assert _parse_retry_after("15", max_delay=10.0) == 10.0
        assert _parse_retry_after("0", max_delay=10.0) == 0.0
        assert _parse_retry_after(None) is None
        assert _parse_retry_after("invalid") is None

    def test_calculate_retry_delay_exponential(self):
        delay_1 = _calculate_retry_delay(
            attempt=1, backoff_factor=0.5, max_delay=10.0, jitter=False
        )
        delay_2 = _calculate_retry_delay(
            attempt=2, backoff_factor=0.5, max_delay=10.0, jitter=False
        )
        delay_3 = _calculate_retry_delay(
            attempt=3, backoff_factor=0.5, max_delay=10.0, jitter=False
        )
        delay_4 = _calculate_retry_delay(
            attempt=4, backoff_factor=0.5, max_delay=10.0, jitter=False
        )

        assert delay_1 == 0.5  # 0.5 * 2^0
        assert delay_2 == 1.0  # 0.5 * 2^1
        assert delay_3 == 2.0  # 0.5 * 2^2
        assert delay_4 == 4.0  # 0.5 * 2^3

    def test_calculate_retry_delay_max_cap(self):
        delay = _calculate_retry_delay(attempt=10, backoff_factor=1.0, max_delay=5.0, jitter=False)
        assert delay == 5.0
