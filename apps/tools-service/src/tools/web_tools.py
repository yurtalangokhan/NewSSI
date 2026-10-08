"""
Web and Search Tools Category.
Provides tools for web search and webpage fetching.

fetch_webpage takes an arbitrary, model-supplied URL and is the SSRF
vector spec TS-6 targets: it now goes through the shared
SecureHTTPClient (packages/security), which refuses loopback,
RFC1918, link-local and cloud-metadata targets and re-validates every
redirect hop. web_search's own outbound calls are not changed here: the
host they hit (duckduckgo.com) is fixed in code, never attacker-supplied,
so they are not an SSRF vector the way fetch_webpage is.
"""

from functools import lru_cache
import html as html_module
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
from localization import t
from security import SecureHTTPClient, UrlPolicyError
from selectolax.parser import HTMLParser

from ..core.base import BaseToolCategory
from ..core.schema import BoundedLimit, ShortText
from .response import tool_error_message

MAX_EXTRACTED_CHARS = 8000
FETCH_MAX_BYTES = 3_000_000


@lru_cache(maxsize=1)
def get_http_client() -> SecureHTTPClient:
    """One client for the process, closed from the server's shutdown hook."""
    return SecureHTTPClient(max_bytes=FETCH_MAX_BYTES)


def clean_text(text: str) -> str:
    """
    Clean text by removing excessive whitespace, HTML entities, and garbage characters.
    """
    if not text:
        return ""

    # Decode HTML entities (&#x27; -> ', &amp; -> &, etc.)
    text = html_module.unescape(text)

    # Remove any remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove URLs that appear in the middle of text (not at the end)
    # Keep URLs that are on their own line

    # Replace multiple spaces/tabs with single space
    text = re.sub(r"[ \t]+", " ", text)

    # Replace multiple newlines with double newline (paragraph break)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]

    # Remove empty lines and very short garbage lines
    cleaned_lines = []
    for line in lines:
        # Skip empty lines or lines with only punctuation/special chars
        if not line or len(line) < 3:
            continue
        # Skip lines that look like garbage (only special characters)
        if re.match(r"^[\s\W]+$", line):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def extract_title_and_description(html: str) -> tuple[str | None, str | None]:
    """Pull <title> and <meta name="description"> out of raw HTML before the
    tag-stripping cleanup pass runs (which otherwise mixes the title text
    into the body with no delimiter).

    Uses the same real parser as _extract_readable_text rather than a
    regex: a `<title>`/`</title>` DOTALL regex swallows everything up to
    the next literal `</title>` in the document, including past an
    unclosed tag, and a name=/content= attribute-order regex misses a
    meta tag whose attributes are simply written the other way round --
    a parser matches both by tag/attribute name, not by source position.
    """
    tree = HTMLParser(html)

    title_node = tree.css_first("title")
    title = clean_text(title_node.text()) if title_node is not None else None
    title = title or None

    meta_node = tree.css_first('meta[name="description"]')
    raw_description = meta_node.attributes.get("content") if meta_node is not None else None
    description = html_module.unescape(raw_description).strip() if raw_description else None
    description = description or None

    return title, description


def _make_ddgs_client():
    """Import seam for tests: returns a DDGS() context-manager instance."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
    return DDGS()


def format_web_search_results(results: list[dict[str, str]]) -> str:
    """Format parsed search results into the fixed TITLE:/URL:/SNIPPET: block
    format WebSearchProgressTracker (agent-service) parses back into
    structured AtlasDocument entries for the sources sidebar. Kept human
    readable so the LLM can still use it as plain text."""
    blocks = [f"TITLE: {r['title']}\nURL: {r['url']}\nSNIPPET: {r['snippet']}" for r in results]
    return "\n---\n".join(blocks)


def web_search_results(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML search. Real implementation
    behind the `web_search` MCP tool — kept as a module-level function so it
    is importable directly in tests (mirrors send_email_message in
    mail_tools.py)."""
    try:
        ddgs_available = True
        try:
            client = _make_ddgs_client()
        except ImportError:
            ddgs_available = False
            client = None

        if ddgs_available and client is not None:
            with client as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))

            if search_results:
                results = [
                    {
                        "title": clean_text(r.get("title", "No title")),
                        "url": r.get("href", ""),
                        "snippet": clean_text(r.get("body", "No description")),
                    }
                    for r in search_results
                ]
                return format_web_search_results(results)

        # Fallback: DuckDuckGo HTML scraping
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = client.get(search_url, headers=headers)
            html = response.text

            result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
            snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>([^<]*(?:<[^>]*>[^<]*)*)</a>'

            links = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)

            clean_snippets = []
            for s in snippets:
                cleaned = clean_text(s)
                if cleaned:
                    clean_snippets.append(cleaned)

            results = []
            for i, (url, title) in enumerate(links[:max_results]):
                if url.startswith("//duckduckgo.com/l/?uddg="):
                    import urllib.parse

                    url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])

                results.append(
                    {
                        "title": clean_text(title),
                        "url": url,
                        "snippet": clean_snippets[i] if i < len(clean_snippets) else "",
                    }
                )

            if not results:
                return _try_instant_answer(client, query, max_results)

            return format_web_search_results(results)

    except Exception as e:  # Final third-party search/tool boundary.
        return t("web.search_error", error=tool_error_message(e))


def _try_instant_answer(client: httpx.Client, query: str, max_results: int) -> str:
    """Try DuckDuckGo Instant Answer API as fallback."""
    try:
        response = client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        data = response.json()

        results: list[dict[str, str]] = []

        if data.get("Abstract"):
            results.append(
                {
                    "title": query,
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["Abstract"],
                }
            )

        related = data.get("RelatedTopics", [])[:max_results]
        results.extend(
            {
                "title": topic["Text"][:80],
                "url": topic.get("FirstURL", ""),
                "snippet": topic["Text"],
            }
            for topic in related
            if isinstance(topic, dict) and topic.get("Text")
        )

        if not results:
            return t("web.no_results", query=query)

        return format_web_search_results(results)

    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return f"No results found for '{query}'"


def _extract_readable_text(raw_html: str) -> str:
    """Strip non-content nodes with a real parser and return cleaned text.

    Replaces a chain of seven `.*?` + re.DOTALL substitutions that scanned
    the entire (possibly attacker-supplied-length) document once per tag
    type -- quadratic-ish behaviour on pathological input, and outright
    wrong on malformed/nested markup a regex cannot track. Comments are
    dropped for free: an HTML parser never surfaces them as text nodes, so
    the previous explicit `<!--.*?-->` removal step is no longer needed.
    """
    tree = HTMLParser(raw_html)
    for selector in ("script", "style", "nav", "footer", "header", "aside", "noscript"):
        for node in tree.css(selector):
            node.decompose()
    body = tree.body or tree.root
    text = body.text(separator=" ", strip=True) if body is not None else ""
    return clean_text(text)


async def fetch_webpage_content(url: str) -> str:
    """Fetch and extract text content from a webpage. Real implementation
    behind the `fetch_webpage` MCP tool — kept as a module-level function so
    it is importable directly in tests.

    url is entirely model-supplied, so this is the SSRF vector spec TS-6
    targets: it goes through the shared SecureHTTPClient rather than a
    bare httpx.Client(follow_redirects=True), which followed a redirect
    to any target -- including cloud metadata endpoints and internal
    services -- with no validation at all.
    """
    try:
        response = await get_http_client().fetch(
            url,
            headers={"User-Agent": "AgenticAI-ToolsService/1.0 (+fetch_webpage)"},
        )
    except UrlPolicyError as e:
        return t("web.url_not_allowed", error=tool_error_message(e), default="URL not allowed")
    except httpx.HTTPError as e:
        return t("web.fetch_error", error=tool_error_message(e))

    if response.status_code >= 400:
        return t(
            "web.fetch_error",
            error=f"upstream returned HTTP {response.status_code}",
        )

    raw_html = response.text
    title, description = extract_title_and_description(raw_html)
    text = _extract_readable_text(raw_html)

    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS] + "\n\n... [truncated]"

    if title is None:
        return text

    header = f"TITLE: {title}"
    if description:
        header += f"\nDESCRIPTION: {description}"
    return f"{header}\n---\n{text}"


class WebTools(BaseToolCategory):
    """Web search and content fetching tools."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return t("categories.web_search.description", default="Web search and webpage content fetching")

    @property
    def label(self) -> str:
        return t("categories.web_search.label", default="Web")

    def register_tools(self, mcp: Any) -> None:
        """Register all web tools with MCP."""

        @mcp.tool()
        def web_search(query: ShortText, max_results: BoundedLimit = 5) -> str:
            """
            Search the web using DuckDuckGo HTML search.
            Works with any language and question formats.

            Args:
                query: The search query (any language, any format)
                max_results: Maximum number of results to return (default: 5)

            Returns:
                Search results as formatted text with titles, snippets and URLs
            """
            return web_search_results(query, max_results)

        @mcp.tool()
        async def fetch_webpage(url: ShortText) -> str:
            """
            Fetch and extract text content from a webpage.

            Args:
                url: The URL to fetch

            Returns:
                The text content of the webpage (cleaned and formatted)
            """
            return await fetch_webpage_content(url)
