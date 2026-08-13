"""
Web and Search Tools Category.
Provides tools for web search and webpage fetching.
"""

import html as html_module
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
from i18n import t

from ..core.base import BaseToolCategory


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
        def web_search(query: str, max_results: int = 5) -> str:
            """
            Search the web using DuckDuckGo HTML search.
            Works with any language and question formats.

            Args:
                query: The search query (any language, any format)
                max_results: Maximum number of results to return (default: 5)

            Returns:
                Search results as formatted text with titles, snippets and URLs
            """
            try:
                # Try ddgs (new package) first, then duckduckgo_search (old)
                ddgs_available = False
                try:
                    from ddgs import DDGS

                    ddgs_available = True
                except ImportError:
                    try:
                        from duckduckgo_search import DDGS

                        ddgs_available = True
                    except ImportError:
                        pass

                if ddgs_available:
                    results = []
                    with DDGS() as ddgs:
                        search_results = list(ddgs.text(query, max_results=max_results))

                        if not search_results:
                            # Don't return yet - fall through to HTML scraping
                            pass
                        else:
                            for i, r in enumerate(search_results, 1):
                                title = clean_text(r.get("title", "No title"))
                                body = clean_text(r.get("body", "No description"))
                                href = r.get("href", "")

                                results.append(f"{i}. **{title}**")
                                if body:
                                    results.append(f"   {body}")
                                if href:
                                    results.append(f"   URL: {href}")
                                results.append("")  # Empty line between results

                            return "\n".join(results).strip()

                # Fallback: DuckDuckGo HTML scraping
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }

                with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                    # Use DuckDuckGo HTML search
                    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
                    response = client.get(search_url, headers=headers)
                    html = response.text

                    results = []

                    # Parse results from HTML
                    # Find all result blocks
                    result_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
                    snippet_pattern = (
                        r'<a[^>]*class="result__snippet"[^>]*>([^<]*(?:<[^>]*>[^<]*)*)</a>'
                    )

                    links = re.findall(result_pattern, html)
                    snippets = re.findall(snippet_pattern, html)

                    # Clean snippets
                    clean_snippets = []
                    for s in snippets:
                        cleaned = clean_text(s)
                        if cleaned:
                            clean_snippets.append(cleaned)

                    for i, (url, title) in enumerate(links[:max_results], 1):
                        title = clean_text(title)
                        snippet = clean_snippets[i - 1] if i - 1 < len(clean_snippets) else ""

                        # Decode URL if needed
                        if url.startswith("//duckduckgo.com/l/?uddg="):
                            import urllib.parse

                            url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])

                        results.append(f"{i}. **{title}**")
                        if snippet:
                            results.append(f"   {snippet}")
                        results.append(f"   URL: {url}")
                        results.append("")  # Empty line between results

                    if not results:
                        # Try instant answer API as last resort
                        return _try_instant_answer(client, query, max_results)

                    return "\n".join(results).strip()

            except Exception as e:
                return t("web.search_error", error=str(e))

        def _try_instant_answer(client: httpx.Client, query: str, max_results: int) -> str:
            """Try DuckDuckGo Instant Answer API as fallback."""
            try:
                response = client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                )
                data = response.json()

                results = []

                if data.get("Abstract"):
                    results.append(f"**Summary:** {data['Abstract']}")
                    if data.get("AbstractURL"):
                        results.append(f"Source: {data['AbstractURL']}")

                related = data.get("RelatedTopics", [])[:max_results]
                for i, topic in enumerate(related, 1):
                    if isinstance(topic, dict) and topic.get("Text"):
                        text = topic["Text"]
                        url = topic.get("FirstURL", "")
                        results.append(f"\n{i}. {text}")
                        if url:
                            results.append(f"   URL: {url}")

                if not results:
                    return t("web.no_results", query=query)

                return "\n".join(results)

            except Exception:
                return f"No results found for '{query}'"

        @mcp.tool()
        def fetch_webpage(url: str) -> str:
            """
            Fetch and extract text content from a webpage.

            Args:
                url: The URL to fetch

            Returns:
                The text content of the webpage (cleaned and formatted)
            """
            try:
                with httpx.Client(follow_redirects=True, timeout=15.0) as client:
                    response = client.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        },
                    )
                    response.raise_for_status()

                    text = response.text

                    # Remove script, style, nav, footer, header elements
                    text = re.sub(
                        r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
                    )
                    text = re.sub(
                        r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
                    )
                    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(
                        r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE
                    )
                    text = re.sub(
                        r"<header[^>]*>.*?</header>", "", text, flags=re.DOTALL | re.IGNORECASE
                    )
                    text = re.sub(
                        r"<aside[^>]*>.*?</aside>", "", text, flags=re.DOTALL | re.IGNORECASE
                    )
                    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

                    # Use clean_text function
                    text = clean_text(text)

                    # Limit response size
                    if len(text) > 8000:
                        text = text[:8000] + "\n\n... [truncated]"

                    return text

            except Exception as e:
                return t("web.fetch_error", error=str(e))
