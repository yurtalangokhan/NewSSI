"""Egnyte source.

Stream ``files``: walks the folder tree below ``root_paths`` with the file
system API (``/pubapi/v1/fs/<path>?list_content=true``). A folder listing holds
``folders`` and ``files`` side by side; both are flattened into items so the
shared tree walker can tell them apart.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import PageRequest, Paginator, StreamSpec, as_iso, from_epoch_millis
from ..common.folder_tree import FolderTreeSource
from ..common.rest_source import parse_iso
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

PAGE_SIZE = 100


class EgnyteConfig(BaseModel):
    domain: str = Field(description="Egnyte domain, e.g. 'acme' for acme.egnyte.com.")
    access_token: str = secret_field(description="OAuth2 access token.")
    root_paths: list[str] = Field(default_factory=lambda: ["/Shared"])
    timeout_seconds: float = 60.0


class EgnyteSource(FolderTreeSource[EgnyteConfig]):
    definition = ConnectorDefinition(
        name="egnyte",
        display_name="Egnyte",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://developers.egnyte.com/docs/read/File_System_Management_API_Documentation",
        icon="egnyte.svg",
        tags=frozenset({"saas", "storage", "documents"}),
    )
    Config = EgnyteConfig

    def base_url(self) -> str:
        domain = self.config.domain
        return domain if domain.startswith("http") else f"https://{domain}.egnyte.com"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="files",
                path="/pubapi/v1/fs/Shared",
                params={"list_content": "true", "count": PAGE_SIZE},
                paginator=_ListingPagination(),
                expand=_split_listing,
                primary_key=("entry_id",),
                cursor_field="last_modified",
                client_side_filter=True,
            )
        ]

    def root_folders(self) -> list[Any]:
        return list(self.config.root_paths)

    def folder_spec(self, spec: StreamSpec, folder: Any) -> StreamSpec:
        return replace(spec, path="/pubapi/v1/fs" + quote(str(folder), safe="/"))

    def subfolder(self, item: dict[str, Any]) -> Any | None:
        return item.get("path") if item.get("is_folder") else None


class _ListingPagination(Paginator):
    """A folder listing pages its *files* with ``count``/``offset``; ``total_count`` says
    how many there are. (The folders come back whole on every page; the walker's
    ``seen`` set keeps them from being queued twice.)"""

    def start(self, req: PageRequest) -> None:
        req.params.setdefault("offset", 0)

    def next(
        self, req: PageRequest, response: httpx.Response, payload: Any, records: list[Any]
    ) -> PageRequest | None:
        if not isinstance(payload, dict):
            return None
        count, total = payload.get("count"), payload.get("total_count")
        if not count or total is None:
            return None
        offset = int(payload.get("offset") or 0) + int(count)
        if offset >= int(total):
            return None
        req.params["offset"] = offset
        return req


def _split_listing(listing: dict[str, Any]) -> Iterator[dict[str, Any]]:
    # Files carry ``last_modified`` as RFC 1123 text, folders ``lastModified`` as epoch
    # milliseconds; both become ISO-8601 so the cursor compares them as times.
    for folder in listing.get("folders") or []:
        yield {**folder, "is_folder": True, "last_modified": _iso(folder.get("lastModified"))}
    for file in listing.get("files") or []:
        yield {**file, "is_folder": False, "last_modified": _iso(file.get("last_modified"))}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return from_epoch_millis(value)
    text = str(value)
    if parse_iso(text) is not None:
        return as_iso(text)
    try:
        return parsedate_to_datetime(text).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return text
