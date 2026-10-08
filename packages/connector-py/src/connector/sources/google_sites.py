"""Google Sites source.

New Google Sites has no content API, so published sites are read the way a
browser would: a breadth-first crawl that stays inside each configured site
URL. Every HTML page becomes a record with its title and extracted text.
Full refresh only (the pages carry no reliable modification time).
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import AsyncIterator
from urllib.parse import urldefrag, urljoin

import httpx
from pydantic import BaseModel, Field

from ..common.rest_source import RestSource
from ..common.text import html_to_text
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncState,
)

_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"'#]+)""", re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class GoogleSitesConfig(BaseModel):
    site_urls: list[str] = Field(
        description="Published site roots, e.g. ['https://sites.google.com/acme.com/handbook']."
    )
    max_pages_per_site: int = Field(default=500, ge=1, le=20_000)
    timeout_seconds: float = 30.0


class GoogleSitesSource(RestSource[GoogleSitesConfig]):
    definition = ConnectorDefinition(
        name="google_sites",
        display_name="Google Sites",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://support.google.com/sites/",
        icon="google_sites.svg",
        tags=frozenset({"google", "web", "crawler"}),
    )
    Config = GoogleSitesConfig

    def base_url(self) -> str:
        return self.config.site_urls[0]

    async def check(self) -> CheckResult:
        try:
            for url in self.config.site_urls:
                await self.request("GET", url, headers={"Accept": "text/html"})
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="pages",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "site": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    source_defined_primary_key=[["url"]],
                )
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        if "pages" not in catalog.names():
            return
        for root in self.config.site_urls:
            async for page in self._crawl(root.rstrip("/")):
                yield Record(stream="pages", data=page)

    async def _crawl(self, root: str) -> AsyncIterator[dict[str, str]]:
        queue: deque[str] = deque([root])
        seen: set[str] = {root}
        fetched = 0
        while queue and fetched < self.config.max_pages_per_site:
            url = queue.popleft()
            try:
                resp = await self.request("GET", url, headers={"Accept": "text/html"})
            except httpx.HTTPStatusError:
                continue
            if "html" not in resp.headers.get("content-type", "html"):
                continue
            fetched += 1
            markup = resp.text
            title = _TITLE.search(markup)
            yield {
                "url": url,
                "site": root,
                "title": html_to_text(title.group(1)) if title else "",
                "content": html_to_text(markup),
            }
            for href in _HREF.findall(markup):
                link = urldefrag(urljoin(url + "/", href))[0].rstrip("/")
                if link.startswith(root) and link not in seen:
                    seen.add(link)
                    queue.append(link)
