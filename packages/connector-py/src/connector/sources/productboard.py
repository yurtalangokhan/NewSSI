"""Productboard source: products, components, features and notes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..base import secret_field
from ..common.declarative import (
    CursorPagination,
    DeclarativeRestSource,
    NextUrlPagination,
    StreamSpec,
    as_iso_z,
)
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_LINKS = NextUrlPagination(next_url_path="links.next")


class ProductboardConfig(BaseModel):
    api_token: str = secret_field(description="Public API access token.")
    timeout_seconds: float = 60.0


class ProductboardSource(DeclarativeRestSource[ProductboardConfig]):
    definition = ConnectorDefinition(
        name="productboard",
        display_name="Productboard",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developer.productboard.com/reference/introduction",
        icon="productboard.svg",
        tags=frozenset({"saas", "product", "feedback"}),
    )
    Config = ProductboardConfig

    def base_url(self) -> str:
        return "https://api.productboard.com"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}", "X-Version": "1"}

    def streams(self) -> list[StreamSpec]:
        def hierarchy(name: str) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/{name}",
                records_path="data",
                paginator=_LINKS,
                cursor_field="updatedAt",
                client_side_filter=True,
                transform=_description_text,
            )

        return [
            hierarchy("products"),
            hierarchy("components"),
            hierarchy("features"),
            StreamSpec(
                name="notes",
                path="/notes",
                records_path="data",
                paginator=CursorPagination(
                    cursor_path="pageCursor",
                    cursor_param="pageCursor",
                    size_param="pageLimit",
                    page_size=100,
                ),
                cursor_field="updatedAt",
                incremental_param="updatedFrom",
                cursor_format=as_iso_z,
                transform=_note_text,
            ),
        ]


def _description_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["description_text"] = html_to_text(rec.get("description"))
    return rec


def _note_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["content_text"] = html_to_text(rec.get("content"))
    return rec
