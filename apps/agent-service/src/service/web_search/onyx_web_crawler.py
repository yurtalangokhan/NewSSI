from __future__ import annotations

import email.utils
import os
import random
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import requests

from core.logger import get_logger
from models.web_search import RenderedPage
from service.web_search.html_utils import ParsedHTML, web_html_cleanup
from service.web_search.models import WebContent, WebContentProvider
from service.web_search.url import (
    DNSResolutionError,
    SSRFBlockedException,
    SSRFException,
    ssrf_safe_get,
)
from service.web_search.web_content import (
    decode_html_bytes,
    extract_pdf_text,
    is_pdf_resource,
    title_from_pdf_metadata,
    title_from_url,
)

logger = get_logger(__name__)


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED = _env_flag_enabled(
    "OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED",
)

DEFAULT_READ_TIMEOUT_SECONDS = 15
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_USER_AGENT = "ATLASWebCrawler/1.0 (+https://atlas.ai)"
DEFAULT_MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_HTML_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_MAX_WORKERS = 5
DEFAULT_MIN_DIRECT_TEXT_LENGTH = 180

# Retry configuration defaults
DEFAULT_MAX_RETRIES = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))
DEFAULT_RETRY_BACKOFF_FACTOR = float(os.getenv("CRAWLER_RETRY_BACKOFF_FACTOR", "0.5"))
DEFAULT_RETRY_MAX_DELAY_SECONDS = 10.0
DEFAULT_RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)
DEFAULT_PLAYWRIGHT_MAX_RETRIES = 1

# Headers that, when present on a 4xx response, signal that the upstream
# is a Cloudflare-style bot challenge (vs. a real auth/not-found error)
# and that retrying via a headless browser is likely to succeed.
_CLOUDFLARE_HEADER_NAMES = ("cf-ray", "cf-mitigated")

# Retriable request exceptions for network-level issues
_RETRIABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.RequestException,
)


class FailureReason:
    CLOUDFLARE_CHALLENGE = (
        "blocked by a Cloudflare bot challenge that the built-in crawler "
        "cannot solve — try a different URL or configure Firecrawl as the "
        "web content provider"
    )
    # Generic 403 with no Cloudflare evidence. Kept distinct from
    # CLOUDFLARE_CHALLENGE so we don't tell the LLM to "configure Firecrawl"
    # for what's actually an auth wall, expired presigned URL, private repo, etc.
    HTTP_403_BLOCKED = (
        "upstream returned HTTP 403 — the URL likely requires authentication "
        "or is otherwise restricted from the built-in crawler"
    )
    SSRF_BLOCKED = "blocked by SSRF protection (URL resolves to an internal address)"
    NETWORK_ERROR = "network error while fetching the URL"
    OVERSIZED_HTML = "HTML response exceeded the configured maximum size"
    OVERSIZED_PDF = "PDF response exceeded the configured maximum size"
    DECODE_ERROR = "could not decode the response body"
    EMPTY_OR_UNPARSEABLE = "response could not be parsed into readable text"

    @staticmethod
    def http_status(status_code: int) -> str:
        return f"upstream returned HTTP {status_code}"


def _failed_result(url: str, failure_reason: str | None = None) -> WebContent:
    return WebContent(
        title="",
        link=url,
        full_content="",
        published_date=None,
        scrape_successful=False,
        failure_reason=failure_reason,
    )


def _has_cloudflare_signals(response: requests.Response) -> bool:
    """True iff the response carries actual Cloudflare-specific markers.

    Strict on purpose — only used to choose between the CF-specific failure
    reason (which tells admins to configure Firecrawl) vs. the generic 403
    failure reason (which points at auth / access). A bare 403 with no
    `cf-ray` / `cf-mitigated` / `Server: cloudflare` headers is treated
    as 'not Cloudflare' here.
    """
    headers = response.headers
    if any(name in headers for name in _CLOUDFLARE_HEADER_NAMES):
        return True
    server = headers.get("Server", "").lower()
    return server.startswith("cloudflare")


def _should_try_playwright_fallback(response: requests.Response) -> bool:
    """True if a Playwright render is plausibly worth attempting.

    Broader than `_has_cloudflare_signals` — any 403 is cheap insurance to
    retry through a real browser (some sites serve JS-protected interstitials
    without CF headers). Real 401/404/410/5xx errors fall through unchanged.
    """
    return response.status_code >= 300 and (
        response.status_code == 403 or _has_cloudflare_signals(response)
    )


def _failure_reason_for_status(response: requests.Response, has_cf_signals: bool) -> str:
    """Pick the LLM-facing failure reason for a 4xx/5xx upstream response.

    Only labels failures as Cloudflare when the response actually carries
    CF-specific headers — bare 403s without those headers are far more
    often auth walls or access-restricted resources, and labelling them
    'Cloudflare' sends the LLM and the admin chasing the wrong fix.
    """
    if has_cf_signals:
        return FailureReason.CLOUDFLARE_CHALLENGE
    if response.status_code == 403:
        return FailureReason.HTTP_403_BLOCKED
    return FailureReason.http_status(response.status_code)


def _parse_html_to_web_content(url: str, html: str) -> WebContent:
    """Run cleanup on raw HTML and shape the result into a WebContent.

    Used by both the fast `requests` path and the Playwright fallback, so
    they emit identical-shape results.
    """
    try:
        parsed: ParsedHTML = web_html_cleanup(html)
        text_content = parsed.cleaned_text or ""
        title = parsed.title or ""
    except Exception as exc:
        logger.warning("ATLAS crawler failed to parse %s (%s)", url, exc.__class__.__name__)
        return _failed_result(url, FailureReason.EMPTY_OR_UNPARSEABLE)

    if not text_content.strip():
        return _failed_result(url, FailureReason.EMPTY_OR_UNPARSEABLE)

    return WebContent(
        title=title,
        link=url,
        full_content=text_content,
        published_date=None,
        scrape_successful=True,
    )


def _looks_like_low_information_content(text: str, min_length: int) -> bool:
    return len(text.strip()) < min_length


def fetch_rendered_html(url: str) -> RenderedPage | None:
    try:
        from service.web_search.playwright_fetch import fetch_rendered_html as _fetch_rendered_html
    except ImportError as exc:
        logger.warning(
            "Playwright fallback unavailable for %s: optional Playwright dependency missing (%s)",
            url,
            exc.__class__.__name__,
        )
        return None

    return _fetch_rendered_html(url)


def looks_like_cloudflare_challenge(html: str) -> bool:
    try:
        from service.web_search.playwright_fetch import (
            looks_like_cloudflare_challenge as _looks_like_cloudflare_challenge,
        )
    except ImportError:
        # Pure HTML string inspection, but it lives beside the optional
        # Playwright import. Without Playwright nothing could have rendered
        # a challenge page anyway, so "not a challenge" is the safe answer.
        return False

    return _looks_like_cloudflare_challenge(html)


def _parse_retry_after(
    retry_after_str: str | None,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY_SECONDS,
) -> float | None:
    """Parse the Retry-After header value into seconds (supports integer or HTTP-date)."""
    if not retry_after_str:
        return None
    retry_after_str = retry_after_str.strip()
    # Try parsing as integer seconds
    try:
        seconds = float(retry_after_str)
        if seconds >= 0:
            return min(seconds, max_delay)
    except ValueError:
        pass
    # Try parsing as HTTP-date
    try:
        date_tuple = email.utils.parsedate_to_datetime(retry_after_str)
        if date_tuple:
            now = datetime.now(UTC)
            if date_tuple.tzinfo is None:
                date_tuple = date_tuple.replace(tzinfo=UTC)
            delta = (date_tuple - now).total_seconds()
            if delta > 0:
                return min(delta, max_delay)
    except Exception:
        pass
    return None


def _calculate_retry_delay(
    attempt: int,
    backoff_factor: float,
    max_delay: float,
    response: requests.Response | None = None,
    jitter: bool = True,
) -> float:
    """Calculate the delay in seconds before the next retry attempt."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        parsed_delay = _parse_retry_after(retry_after, max_delay=max_delay)
        if parsed_delay is not None:
            return parsed_delay

    delay = backoff_factor * (2 ** max(0, attempt - 1))
    if jitter:
        delay += random.uniform(0, min(0.25 * delay, 0.5))
    return min(delay, max_delay)


class OnyxWebCrawler(WebContentProvider):
    """
    Lightweight built-in crawler that fetches HTML directly and extracts readable text.
    Acts as the default content provider (ATLAS Web Crawler) when no external crawler
    (e.g. Firecrawl) is configured.

    Includes a robust, configurable retry mechanism with exponential backoff and jitter
    for automatically recovering from connection drops, transient DNS glitches,
    network timeouts, and transient HTTP status codes (408, 429, 500, 502, 503, 504).

    On a Cloudflare/bot-challenge response (canonical entry point: HTTP 403,
    or any response carrying a `cf-ray` / `cf-mitigated` header), falls back
    to a headless-browser fetch via `playwright_fetch`. Controlled
    by the `OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED` flag.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pdf_size_bytes: int | None = None,
        max_html_size_bytes: int | None = None,
        min_direct_text_length: int = DEFAULT_MIN_DIRECT_TEXT_LENGTH,
        playwright_fallback_enabled: bool = OPEN_URL_PLAYWRIGHT_FALLBACK_ENABLED,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_factor: float = DEFAULT_RETRY_BACKOFF_FACTOR,
        retry_max_delay_seconds: float = DEFAULT_RETRY_MAX_DELAY_SECONDS,
        retry_status_codes: Sequence[int] = DEFAULT_RETRY_STATUS_CODES,
        playwright_max_retries: int = DEFAULT_PLAYWRIGHT_MAX_RETRIES,
        retry_jitter: bool = True,
    ) -> None:
        self._read_timeout_seconds = timeout_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._max_pdf_size_bytes = max_pdf_size_bytes
        self._max_html_size_bytes = max_html_size_bytes
        self._min_direct_text_length = min_direct_text_length
        self._playwright_fallback_enabled = playwright_fallback_enabled
        self._max_retries = max(0, max_retries)
        self._retry_backoff_factor = max(0.0, retry_backoff_factor)
        self._retry_max_delay_seconds = max(0.0, retry_max_delay_seconds)
        self._retry_status_codes = set(retry_status_codes)
        self._playwright_max_retries = max(0, playwright_max_retries)
        self._retry_jitter = retry_jitter
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def retry_backoff_factor(self) -> float:
        return self._retry_backoff_factor

    @property
    def retry_status_codes(self) -> set[int]:
        return self._retry_status_codes

    def contents(self, urls: Sequence[str]) -> list[WebContent]:
        if not urls:
            return []

        max_workers = min(DEFAULT_MAX_WORKERS, len(urls))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(self._fetch_url_safe, urls))

    def _fetch_url_safe(self, url: str) -> WebContent:
        """Wrapper that catches all exceptions so one bad URL doesn't kill the batch."""
        try:
            return self._fetch_url(url)
        except Exception as exc:
            logger.warning(
                "ATLAS crawler unexpected error for %s (%s)",
                url,
                exc.__class__.__name__,
            )
            return _failed_result(url, FailureReason.NETWORK_ERROR)

    def _fetch_url(self, url: str) -> WebContent:
        total_attempts = self._max_retries + 1

        for attempt in range(1, total_attempts + 1):
            is_last_attempt = attempt >= total_attempts
            try:
                response = ssrf_safe_get(
                    url,
                    headers=self._headers,
                    timeout=(self._connect_timeout_seconds, self._read_timeout_seconds),
                )
            except SSRFBlockedException as exc:
                # Permanent SSRF violation (e.g. private IP or blocked host). Do not retry.
                logger.error(
                    "SSRF protection permanently blocked request to %s (%s)",
                    url,
                    exc.__class__.__name__,
                )
                return _failed_result(url, FailureReason.SSRF_BLOCKED)
            except DNSResolutionError as exc:
                # Transient DNS resolution error — retry if attempts remain.
                if not is_last_attempt:
                    delay = _calculate_retry_delay(
                        attempt,
                        self._retry_backoff_factor,
                        self._retry_max_delay_seconds,
                        jitter=self._retry_jitter,
                    )
                    logger.warning(
                        "ATLAS crawler DNS resolution failed for %s (attempt %d/%d): %s. Retrying in %.2fs...",
                        url,
                        attempt,
                        total_attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                logger.warning(
                    "ATLAS crawler DNS resolution failed for %s after %d attempts (%s)",
                    url,
                    total_attempts,
                    exc.__class__.__name__,
                )
                return _failed_result(url, FailureReason.NETWORK_ERROR)
            except SSRFException as exc:
                # Generic fallback for any other SSRF exception. Do not retry.
                logger.error(
                    "SSRF protection blocked request to %s (%s)",
                    url,
                    exc.__class__.__name__,
                )
                return _failed_result(url, FailureReason.SSRF_BLOCKED)
            except _RETRIABLE_EXCEPTIONS as exc:
                # Transient network, connection reset, or timeout error.
                if not is_last_attempt:
                    delay = _calculate_retry_delay(
                        attempt,
                        self._retry_backoff_factor,
                        self._retry_max_delay_seconds,
                        jitter=self._retry_jitter,
                    )
                    logger.warning(
                        "ATLAS crawler connection error for %s (attempt %d/%d): %s (%s). Retrying in %.2fs...",
                        url,
                        attempt,
                        total_attempts,
                        exc.__class__.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                    continue

                logger.warning(
                    "ATLAS crawler failed to fetch %s after %d attempts (%s)",
                    url,
                    total_attempts,
                    exc.__class__.__name__,
                )
                return _failed_result(url, FailureReason.NETWORK_ERROR)
            except Exception as exc:
                # Non-retriable exception (e.g. ValueError).
                logger.warning(
                    "ATLAS crawler unexpected error fetching %s: %s",
                    url,
                    exc,
                )
                return _failed_result(url, FailureReason.NETWORK_ERROR)

            # Check for retriable HTTP status codes (e.g. 408, 429, 500, 502, 503, 504)
            if response.status_code in self._retry_status_codes and not is_last_attempt:
                delay = _calculate_retry_delay(
                    attempt,
                    self._retry_backoff_factor,
                    self._retry_max_delay_seconds,
                    response=response,
                    jitter=self._retry_jitter,
                )
                logger.warning(
                    "ATLAS crawler received HTTP %d for %s (attempt %d/%d). Retrying in %.2fs...",
                    response.status_code,
                    url,
                    attempt,
                    total_attempts,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                has_cf_signals = _has_cloudflare_signals(response)
                try_fallback = (
                    self._playwright_fallback_enabled and _should_try_playwright_fallback(response)
                )

                if try_fallback:
                    logger.info(
                        "ATLAS crawler got %s for %s; retrying via Playwright (cf_signals=%s)",
                        response.status_code,
                        url,
                        has_cf_signals,
                    )
                    fallback = self._fetch_via_playwright(url)
                    if fallback is not None:
                        return fallback

                logger.warning("ATLAS crawler received %s for %s", response.status_code, url)
                return _failed_result(url, _failure_reason_for_status(response, has_cf_signals))

            content_type = response.headers.get("Content-Type", "")
            content = response.content

            content_sniff = content[:1024] if content else None
            if is_pdf_resource(url, content_type, content_sniff):
                return self._handle_pdf_response(url, content)

            if self._max_html_size_bytes is not None and len(content) > self._max_html_size_bytes:
                logger.warning(
                    "HTML content too large (%d bytes) for %s, max is %d",
                    len(content),
                    url,
                    self._max_html_size_bytes,
                )
                return _failed_result(url, FailureReason.OVERSIZED_HTML)

            try:
                decoded_html = decode_html_bytes(
                    content,
                    content_type=content_type,
                    fallback_encoding=response.apparent_encoding or response.encoding,
                )
            except Exception as exc:
                logger.warning(
                    "ATLAS crawler failed to decode %s (%s)", url, exc.__class__.__name__
                )
                return _failed_result(url, FailureReason.DECODE_ERROR)

            direct_result = _parse_html_to_web_content(url, decoded_html)

            if not self._playwright_fallback_enabled:
                return direct_result

            if not direct_result.scrape_successful:
                logger.info(
                    "Direct HTML parse failed for %s; retrying via Playwright",
                    url,
                )
                fallback = self._fetch_via_playwright(url)
                return fallback or direct_result

            if _looks_like_low_information_content(
                direct_result.full_content, self._min_direct_text_length
            ):
                logger.info(
                    "Direct HTML parse returned low-information content for %s; "
                    "retrying via Playwright",
                    url,
                )
                fallback = self._fetch_via_playwright(url)
                if fallback is not None and fallback.scrape_successful:
                    return fallback

            return direct_result

        return _failed_result(url, FailureReason.NETWORK_ERROR)

    def _handle_pdf_response(self, url: str, content: bytes) -> WebContent:
        if self._max_pdf_size_bytes is not None and len(content) > self._max_pdf_size_bytes:
            logger.warning(
                "PDF content too large (%d bytes) for %s, max is %d",
                len(content),
                url,
                self._max_pdf_size_bytes,
            )
            return _failed_result(url, FailureReason.OVERSIZED_PDF)
        text_content, metadata = extract_pdf_text(content)
        title = title_from_pdf_metadata(metadata) or title_from_url(url)
        if not text_content.strip():
            return _failed_result(url, FailureReason.EMPTY_OR_UNPARSEABLE)
        return WebContent(
            title=title,
            link=url,
            full_content=text_content,
            published_date=None,
            scrape_successful=True,
        )

    def _fetch_via_playwright(self, url: str) -> WebContent | None:
        """Try headless render with retries for transient navigation errors."""
        total_pw_attempts = self._playwright_max_retries + 1
        for pw_attempt in range(1, total_pw_attempts + 1):
            rendered: RenderedPage | None = fetch_rendered_html(url)
            if rendered is None:
                if pw_attempt < total_pw_attempts:
                    time.sleep(0.5)
                    continue
                return None

            if (
                self._max_html_size_bytes is not None
                and len(rendered.html) > self._max_html_size_bytes
            ):
                logger.warning(
                    "Rendered HTML too large (%d chars) for %s, max is %d",
                    len(rendered.html),
                    url,
                    self._max_html_size_bytes,
                )
                return None

            # If the render came back as a CF challenge interstitial, surface
            # that as a definitive CF failure (parsing it would just leak
            # "Just a moment..." text to the LLM). This is the one case where
            # Playwright actually adds information vs. the original 4xx.
            if looks_like_cloudflare_challenge(rendered.html):
                logger.info(
                    "Playwright fallback rendered the Cloudflare challenge page "
                    "itself for %s; treating as Cloudflare failure",
                    url,
                )
                return _failed_result(url, FailureReason.CLOUDFLARE_CHALLENGE)

            result = _parse_html_to_web_content(url, rendered.html)
            if not result.scrape_successful:
                return None
            logger.info("Playwright fallback succeeded for %s", url)
            return result

        return None


# Alias for ATLAS Web Crawler
AtlasWebCrawler = OnyxWebCrawler
