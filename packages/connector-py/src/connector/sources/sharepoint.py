"""SharePoint Online source via Microsoft Graph.

Streams for one site (``site`` = ``{hostname}:/sites/{path}`` or a site id):

* ``pages``       – modern site pages with their text content (canvas web parts)
* ``drive_items`` – files across the site's document libraries (metadata +
                    time-limited download URL); incremental through the Graph
                    *delta* API, whose ``deltaLink`` is the stored state
* ``list_items``  – rows of the lists named in ``lists`` (fields expanded)

Requires application permissions ``Sites.Read.All`` (and ``Files.Read.All``
for drive items). File *content* is not downloaded here; the record carries
``download_url`` for the ingestion layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import Field

from ..common.cursor import is_newer, later
from ..common.microsoft_graph import (
    GraphConfigBase,
    GraphSource,
    drive_item_record,
    keep_drive_item,
)
from ..common.text import html_to_text
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

#: ``(stream state) -> (record | None, new state | None)`` pairs.
_StreamReader = Callable[
    [dict[str, Any]], AsyncIterator[tuple[dict[str, Any] | None, dict[str, Any] | None]]
]


class SharePointConfig(GraphConfigBase):
    site: str = Field(
        description="Site id, or '{hostname}:/sites/{name}' e.g. 'acme.sharepoint.com:/sites/hr'."
    )
    lists: list[str] | None = Field(default=None, description="List names/ids for `list_items`.")
    drives: list[str] | None = Field(
        default=None, description="Document library names/ids. Default: every drive of the site."
    )
    file_extensions: list[str] | None = Field(
        default=None, description="Only emit files with these extensions, e.g. ['pdf', 'docx']."
    )
    include_folders: bool = False


class SharePointSource(GraphSource[SharePointConfig]):
    definition = ConnectorDefinition(
        name="sharepoint",
        display_name="SharePoint Online",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://learn.microsoft.com/graph/api/resources/sharepoint",
        icon="sharepoint.svg",
        tags=frozenset({"saas", "microsoft", "documents"}),
    )
    Config = SharePointConfig

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    @property
    def _site(self) -> str:
        return f"/sites/{self.config.site}"

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="pages",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "name": {"type": "string"},
                            "web_url": {"type": "string"},
                            "content": {"type": "string"},
                            "last_modified": {"type": "string", "format": "date-time"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
                Stream(
                    name="drive_items",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "drive_id": {"type": "string"},
                            "name": {"type": "string"},
                            "path": {"type": "string"},
                            "is_folder": {"type": "boolean"},
                            "size": {"type": "integer"},
                            "mime_type": {"type": "string"},
                            "web_url": {"type": "string"},
                            "download_url": {"type": "string"},
                            "deleted": {"type": "boolean"},
                            "last_modified": {"type": "string", "format": "date-time"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
                Stream(
                    name="list_items",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "list": {"type": "string"},
                            "web_url": {"type": "string"},
                            "fields": {"type": "object"},
                            "last_modified": {"type": "string", "format": "date-time"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["last_modified"],
                    source_defined_primary_key=[["id"]],
                ),
            ]
        )

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for configured in catalog.streams:
            name = configured.stream.name
            incremental = configured.sync_mode is SyncMode.INCREMENTAL
            stream_state = state.get(name) if incremental else {}
            reader = self._readers().get(name)
            if reader is None:
                continue
            async for item, new_state in reader(stream_state):
                if item is not None:
                    yield Record(stream=name, data=item)
                if new_state is not None and incremental:
                    yield State(stream=name, data=new_state)

    def _readers(self) -> dict[str, _StreamReader]:
        return {
            "pages": self._pages,
            "drive_items": self._drive_items,
            "list_items": self._list_items,
        }

    # ---- pages ----------------------------------------------------------------------

    async def _pages(
        self, st: dict[str, Any]
    ) -> AsyncIterator[tuple[dict[str, Any] | None, dict | None]]:
        last = st.get("cursor")
        max_seen = last
        params = {"$expand": "canvasLayout", "$top": self.config.page_size}
        async for raw in self.paginate(
            f"{self._site}/pages/microsoft.graph.sitePage", params=params
        ):
            modified = raw.get("lastModifiedDateTime")
            if last and modified and not is_newer(modified, last):
                continue
            max_seen = later(max_seen, modified)
            yield (
                {
                    "id": raw.get("id"),
                    "title": raw.get("title"),
                    "name": raw.get("name"),
                    "web_url": raw.get("webUrl"),
                    "content": _canvas_text(raw.get("canvasLayout") or {}),
                    "last_modified": modified,
                },
                None,
            )
        if max_seen:
            yield None, {"cursor": max_seen}

    # ---- drive items (delta) ----------------------------------------------------

    async def _drives(self) -> list[dict[str, Any]]:
        drives = [d async for d in self.paginate(f"{self._site}/drives")]
        if self.config.drives:
            wanted = set(self.config.drives)
            drives = [d for d in drives if d.get("name") in wanted or d.get("id") in wanted]
        return drives

    async def _drive_items(
        self, st: dict[str, Any]
    ) -> AsyncIterator[tuple[dict[str, Any] | None, dict | None]]:
        delta_links: dict[str, str] = dict(st.get("delta_links") or {})
        new_links: dict[str, str] = {}
        for drive in await self._drives():
            drive_id = drive["id"]
            changes = self.delta(
                f"/drives/{drive_id}/root/delta", resume_from=delta_links.get(drive_id)
            )
            async for raw in changes:
                if not keep_drive_item(
                    raw,
                    include_folders=self.config.include_folders,
                    file_extensions=self.config.file_extensions,
                ):
                    continue
                record = drive_item_record(raw)
                record.update(drive_id=drive_id, drive_name=drive.get("name"))
                yield record, None
            if changes.delta_link:
                new_links[drive_id] = changes.delta_link
        if new_links:
            yield None, {"delta_links": {**delta_links, **new_links}}

    # ---- list items --------------------------------------------------------------

    async def _list_items(
        self, st: dict[str, Any]
    ) -> AsyncIterator[tuple[dict[str, Any] | None, dict | None]]:
        if not self.config.lists:
            return
        last = st.get("cursor")
        max_seen = last
        for list_ref in self.config.lists:
            params = {"$expand": "fields", "$top": self.config.page_size}
            async for raw in self.paginate(f"{self._site}/lists/{list_ref}/items", params=params):
                modified = raw.get("lastModifiedDateTime")
                if last and modified and not is_newer(modified, last):
                    continue
                max_seen = later(max_seen, modified)
                fields = raw.get("fields") or {}
                yield (
                    {
                        "id": raw.get("id"),
                        "list": list_ref,
                        "web_url": raw.get("webUrl"),
                        "fields": {k: v for k, v in fields.items() if not k.startswith("@odata")},
                        "last_modified": modified,
                    },
                    None,
                )
        if max_seen:
            yield None, {"cursor": max_seen}


def _canvas_text(canvas: dict[str, Any]) -> str:
    """Flatten a sitePage canvasLayout into text (text web parts only)."""
    parts: list[str] = []
    for section in canvas.get("horizontalSections") or []:
        for column in section.get("columns") or []:
            for wp in column.get("webparts") or []:
                html = wp.get("innerHtml")
                if html:
                    parts.append(html_to_text(html))
    vertical = canvas.get("verticalSection") or {}
    for wp in vertical.get("webparts") or []:
        html = wp.get("innerHtml")
        if html:
            parts.append(html_to_text(html))
    return "\n\n".join(p for p in parts if p)
