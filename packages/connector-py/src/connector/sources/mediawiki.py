"""MediaWiki source (any wiki running MediaWiki, including Wikipedia).

One stream, ``pages``: wikitext plus last revision timestamp. What is read is
decided by the config: explicit ``titles``, members of ``categories``, or every
page of the selected ``namespaces``. Paging follows the API's ``continue``
object. There is no server-side modification filter for these generators, so
incremental sync filters client-side on the revision timestamp.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import ContinueParamsPagination, DeclarativeRestSource, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_BASE_PARAMS: dict[str, Any] = {
    "action": "query",
    "format": "json",
    "formatversion": 2,
    "prop": "revisions|info",
    "rvprop": "content|timestamp|ids",
    "rvslots": "main",
    "inprop": "url",
}
_BATCH = 50  # API limit when revision content is requested


class WikiScope(BaseModel):
    """What to read from a wiki, whichever site it is."""

    titles: list[str] | None = Field(default=None, description="Read exactly these pages.")
    categories: list[str] | None = Field(default=None, description="Read members of these.")
    namespaces: list[int] = Field(default_factory=lambda: [0], description="For a full crawl.")
    bearer_token: str | None = secret_field(default=None, description="OAuth2 token, if private.")
    user_agent: str = "connector-py/0.1 (mediawiki source)"
    timeout_seconds: float = 60.0
    verify_ssl: bool = True


class MediaWikiSite(BaseModel):
    api_url: str = Field(description="URL of api.php, e.g. https://wiki.acme.com/w/api.php")


class MediaWikiConfig(WikiScope, MediaWikiSite):
    """Where the wiki is (listed first in the form), then what to read from it."""


WikiConfigT = TypeVar("WikiConfigT", bound=WikiScope)


class WikiSource(DeclarativeRestSource[WikiConfigT]):
    """Reader for any MediaWiki API. A subclass says where ``api.php`` is."""

    def api_url(self) -> str:
        raise NotImplementedError

    def base_url(self) -> str:
        return self.api_url().rsplit("/", 1)[0]

    def auth_headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.config.user_agent}
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        return headers

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="pages",
                path=self.api_url(),
                records_path="query.pages",
                params=self._targets()[0],
                paginator=ContinueParamsPagination(),
                primary_key=("pageid",),
                cursor_field="updated_at",
                client_side_filter=True,
                transform=_to_record,
            )
        ]

    def _targets(self) -> list[dict[str, Any]]:
        """One parameter set per request series (title batch, category, namespace)."""
        cfg = self.config
        if cfg.titles:
            return [
                {**_BASE_PARAMS, "titles": "|".join(cfg.titles[i : i + _BATCH])}
                for i in range(0, len(cfg.titles), _BATCH)
            ]
        if cfg.categories:
            return [
                {
                    **_BASE_PARAMS,
                    "generator": "categorymembers",
                    "gcmtitle": c if c.lower().startswith("category:") else f"Category:{c}",
                    "gcmlimit": _BATCH,
                    "gcmtype": "page",
                }
                for c in cfg.categories
            ]
        return [
            {**_BASE_PARAMS, "generator": "allpages", "gaplimit": _BATCH, "gapnamespace": ns}
            for ns in cfg.namespaces
        ]

    async def _read_records(self, spec: StreamSpec, cursor: Any) -> AsyncIterator[dict[str, Any]]:
        seen: set[Any] = set()
        for params in self._targets():
            async for rec in self._read_pages(replace(spec, params=params), None, cursor):
                if rec.get("pageid") in seen:
                    continue
                seen.add(rec.get("pageid"))
                yield rec


class MediaWikiSource(WikiSource[MediaWikiConfig]):
    definition = ConnectorDefinition(
        name="mediawiki",
        display_name="MediaWiki",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://www.mediawiki.org/wiki/API:Main_page",
        icon="mediawiki.svg",
        tags=frozenset({"wiki", "self-hosted"}),
    )
    Config = MediaWikiConfig

    def api_url(self) -> str:
        return self.config.api_url


def _to_record(page: dict[str, Any]) -> dict[str, Any] | None:
    if page.get("missing") or page.get("invalid"):
        return None
    revision = (page.get("revisions") or [{}])[0]
    return {
        "pageid": page.get("pageid"),
        "title": page.get("title"),
        "namespace": page.get("ns"),
        "url": page.get("fullurl"),
        "revision_id": revision.get("revid"),
        "content": ((revision.get("slots") or {}).get("main") or {}).get("content"),
        "updated_at": revision.get("timestamp") or page.get("touched"),
    }
