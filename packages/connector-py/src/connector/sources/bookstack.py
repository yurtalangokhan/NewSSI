"""BookStack source: shelves, books, chapters and pages (with HTML/markdown body)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, OffsetPagination, StreamSpec
from ..common.rest_source import parse_iso
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = OffsetPagination(
    limit_param="count", offset_param="offset", page_size=100, total_path="total"
)


def _filter_date(value: Any) -> str:
    parsed = parse_iso(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else str(value)


class BookStackConfig(BaseModel):
    base_url: str = Field(description="e.g. https://docs.acme.com")
    token_id: str = secret_field(description="API token id.")
    token_secret: str = secret_field(description="API token secret.")
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class BookStackSource(DeclarativeRestSource[BookStackConfig]):
    definition = ConnectorDefinition(
        name="bookstack",
        display_name="BookStack",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://demo.bookstackapp.com/api/docs",
        icon="bookstack.svg",
        tags=frozenset({"wiki", "self-hosted"}),
    )
    Config = BookStackConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.config.token_id}:{self.config.token_secret}"}

    def streams(self) -> list[StreamSpec]:
        def listing(name: str, detail: bool = False) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/api/{name}",
                records_path="data",
                params={"sort": "+updated_at"},
                paginator=_PAGER,
                cursor_field="updated_at",
                incremental_param="filter[updated_at:gt]",
                cursor_format=_filter_date,
                detail_path=f"/api/{name}/{{record[id]}}" if detail else None,
            )

        return [listing("shelves"), listing("books"), listing("chapters"), listing("pages", True)]
