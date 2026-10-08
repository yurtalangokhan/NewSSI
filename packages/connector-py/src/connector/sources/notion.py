"""Notion source.

Streams ``pages`` and ``databases`` come from the ``/v1/search`` endpoint, which
only returns what has been shared with the integration. With
``include_content`` the block tree of every page is walked and flattened into
a ``content`` text field. The search endpoint cannot filter by time, so
incremental sync sorts ascending by ``last_edited_time`` and filters client-side.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = CursorPagination(
    cursor_path="next_cursor",
    cursor_param="start_cursor",
    in_body=True,
    size_param="page_size",
    page_size=100,
    has_more_path="has_more",
)


class NotionConfig(BaseModel):
    token: str = secret_field(description="Internal integration secret.")
    include_content: bool = Field(default=True, description="Fetch and flatten page blocks.")
    max_block_depth: int = Field(default=3, ge=0, le=10)
    notion_version: str = "2022-06-28"
    timeout_seconds: float = 60.0


class NotionSource(DeclarativeRestSource[NotionConfig]):
    definition = ConnectorDefinition(
        name="notion",
        display_name="Notion",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://developers.notion.com/reference",
        icon="notion.svg",
        tags=frozenset({"saas", "wiki", "docs"}),
    )
    Config = NotionConfig

    def base_url(self) -> str:
        return "https://api.notion.com"

    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Notion-Version": self.config.notion_version,
        }

    def streams(self) -> list[StreamSpec]:
        def search(name: str, obj: str, enrich: str | None) -> StreamSpec:
            return StreamSpec(
                name=name,
                path="/v1/search",
                method="POST",
                body={
                    "filter": {"property": "object", "value": obj},
                    "sort": {"direction": "ascending", "timestamp": "last_edited_time"},
                },
                records_path="results",
                paginator=_PAGER,
                cursor_field="last_edited_time",
                client_side_filter=True,
                enrich=enrich,
                transform=_flatten,
            )

        return [
            search("pages", "page", "_load_blocks" if self.config.include_content else None),
            search("databases", "database", None),
        ]

    async def _load_blocks(self, rec: dict[str, Any], parent: Any) -> dict[str, Any]:
        rec["content"] = "\n".join(await self._block_text(rec["id"], 0))
        return rec

    async def _block_text(self, block_id: str, depth: int) -> list[str]:
        lines: list[str] = []
        params: dict[str, Any] = {"page_size": 100}
        while True:
            page = await self.get_json(f"/v1/blocks/{block_id}/children", params=params)
            for block in page.get("results", []) or []:
                payload = block.get(block.get("type", ""), {}) or {}
                text = _plain(payload.get("rich_text") or payload.get("text") or [])
                if text:
                    lines.append(text)
                if block.get("has_children") and depth < self.config.max_block_depth:
                    lines.extend(await self._block_text(block["id"], depth + 1))
            if not page.get("has_more") or not page.get("next_cursor"):
                return lines
            params["start_cursor"] = page["next_cursor"]


def _plain(rich_text: list[dict[str, Any]]) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text if isinstance(part, dict))


def _flatten(rec: dict[str, Any]) -> dict[str, Any]:
    title = ""
    if isinstance(rec.get("title"), list):  # databases
        title = _plain(rec["title"])
    else:
        for prop in (rec.get("properties") or {}).values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title = _plain(prop.get("title") or [])
                break
    rec["title_text"] = title
    return rec
