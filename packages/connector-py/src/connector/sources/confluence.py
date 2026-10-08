"""Confluence source (Cloud and Data Center) over the REST v1 content API.

Streams:

* ``spaces``     – space metadata
* ``pages``      – pages with storage-format body (HTML) and version info
* ``blogposts``  – blog posts, same shape as pages

Incremental sync for ``pages``/``blogposts`` uses CQL ``lastmodified >`` on the
``version.when`` timestamp. Auth: e-mail + API token (Cloud, basic) or a
personal access token (Data Center, bearer).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.atlassian_auth import atlassian_auth_headers, user_time_zone
from ..common.cursor import CursorTracker
from ..common.rest_source import RestSource, parse_iso
from ..common.rest_source import iso_or_none as _iso
from ..models import (
    Catalog,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)

CONTENT_EXPAND = "body.storage,version,space,ancestors,metadata.labels"


class ConfluenceConfig(BaseModel):
    base_url: str = Field(
        description="e.g. https://acme.atlassian.net/wiki (Cloud) or https://confluence.acme.com"
    )
    auth_type: Literal["basic", "bearer"] = Field(
        default="basic",
        description="basic = e-mail + API token (Cloud); bearer = PAT (Data Center).",
    )
    email: str | None = None
    api_token: str | None = secret_field(default=None, description="API token or PAT.")
    space_keys: list[str] | None = Field(default=None, description="Restrict to these spaces.")
    include_body: bool = Field(default=True, description="Fetch page body (storage HTML).")
    page_size: int = Field(default=50, ge=1, le=250)
    timezone: str | None = Field(
        default=None,
        description="IANA zone CQL dates are rendered in. Default: the API user's profile "
        "zone (Confluence reads CQL dates in it), UTC when the profile has none.",
    )
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class ConfluenceSource(RestSource[ConfluenceConfig]):
    definition = ConnectorDefinition(
        name="confluence",
        display_name="Confluence",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://developer.atlassian.com/cloud/confluence/rest/v1/",
        icon="confluence.svg",
        tags=frozenset({"saas", "atlassian", "wiki"}),
    )
    Config = ConfluenceConfig
    check_path: ClassVar[str] = "/rest/api/space?limit=1"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return atlassian_auth_headers(
            self.config.auth_type, self.config.email, self.config.api_token
        )

    # ---- catalog -----------------------------------------------------------------

    async def discover(self) -> Catalog:
        content = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "type": {"type": "string"},
                "status": {"type": "string"},
                "space_key": {"type": "string"},
                "url": {"type": "string"},
                "body_html": {"type": "string"},
                "labels": {"type": "array"},
                "ancestors": {"type": "array"},
                "version": {"type": "integer"},
                "updated_at": {"type": "string", "format": "date-time"},
                "updated_by": {"type": "string"},
            },
        }
        return Catalog(
            streams=[
                Stream(
                    name="spaces",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "key": {"type": "string"},
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                        },
                    },
                    source_defined_primary_key=[["key"]],
                ),
                Stream(
                    name="pages",
                    json_schema=content,
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["updated_at"],
                    source_defined_primary_key=[["id"]],
                ),
                Stream(
                    name="blogposts",
                    json_schema=content,
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["updated_at"],
                    source_defined_primary_key=[["id"]],
                ),
            ]
        )

    # ---- read ----------------------------------------------------------------------

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for configured in catalog.streams:
            name = configured.stream.name
            if name == "spaces":
                async for space in self._spaces():
                    yield Record(stream=name, data=space)
            elif name in ("pages", "blogposts"):
                tracker = CursorTracker(
                    name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
                )
                content_type = "page" if name == "pages" else "blogpost"
                async for item in self._content(content_type, tracker.start):
                    tracker.observe(item["updated_at"])
                    yield Record(stream=name, data=item)
                if final := tracker.final_state():
                    yield final

    async def _spaces(self) -> AsyncIterator[dict[str, Any]]:
        params: dict[str, Any] = {"limit": self.config.page_size, "start": 0}
        if self.config.space_keys:
            params["spaceKey"] = self.config.space_keys
        async for raw in self._paginate("/rest/api/space", params):
            yield {
                "id": raw.get("id"),
                "key": raw.get("key"),
                "name": raw.get("name"),
                "type": raw.get("type"),
                "url": _absolute(self.config.base_url, raw.get("_links", {}).get("webui")),
            }

    async def _content(self, content_type: str, since: str | None) -> AsyncIterator[dict[str, Any]]:
        cql = [f"type={content_type}"]
        if self.config.space_keys:
            keys = ",".join(f'"{k}"' for k in self.config.space_keys)
            cql.append(f"space in ({keys})")
        if since:
            stamp = parse_iso(since)
            if stamp:
                # Confluence reads the literal in the API user's profile zone.
                zone = await user_time_zone(self, "/rest/api/user/current", self.config.timezone)
                cql.append(f'lastmodified > "{stamp.astimezone(zone).strftime("%Y-%m-%d %H:%M")}"')
        params = {
            "cql": " and ".join(cql) + " order by lastmodified asc",
            "limit": self.config.page_size,
            "start": 0,
            "expand": CONTENT_EXPAND if self.config.include_body else "version,space",
        }
        async for raw in self._paginate("/rest/api/content/search", params):
            yield self._to_record(raw)

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        params = dict(params)
        while True:
            page = await self.get_json(path, params=params)
            results = page.get("results", []) or []
            for item in results:
                yield item
            size = page.get("size", len(results))
            links = page.get("_links")
            if links is not None:
                # Permission filtering returns short pages with more to come: ``next`` decides.
                more = "next" in links
            else:
                more = size >= page.get("limit", params.get("limit", self.config.page_size))
            if not results or not more:
                return
            params["start"] = int(params.get("start", 0)) + size

    def _to_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        version = raw.get("version") or {}
        by = version.get("by") or {}
        return {
            "id": str(raw.get("id")),
            "title": raw.get("title"),
            "type": raw.get("type"),
            "status": raw.get("status"),
            "space_key": (raw.get("space") or {}).get("key"),
            "url": _absolute(self.config.base_url, (raw.get("_links") or {}).get("webui")),
            "body_html": ((raw.get("body") or {}).get("storage") or {}).get("value"),
            "labels": [
                lab.get("name")
                for lab in ((raw.get("metadata") or {}).get("labels") or {}).get("results", [])
            ],
            "ancestors": [a.get("title") for a in raw.get("ancestors") or []],
            "version": version.get("number"),
            "updated_at": _iso(version.get("when")),
            "updated_by": by.get("displayName") or by.get("email"),
        }


def _absolute(base: str, path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return base.rstrip("/") + path
