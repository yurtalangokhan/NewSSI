"""Guru source: cards (with HTML content flattened to text) and collections."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, LinkHeaderPagination, StreamSpec
from ..common.rest_source import basic_auth_header
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class GuruConfig(BaseModel):
    username: str = Field(description="E-mail of the API user.")
    api_token: str = secret_field(description="User or collection token.")
    query: str | None = Field(default=None, description="Optional Guru Query Language filter.")
    timeout_seconds: float = 30.0


class GuruSource(DeclarativeRestSource[GuruConfig]):
    definition = ConnectorDefinition(
        name="guru",
        display_name="Guru",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://developer.getguru.com/",
        icon="guru.svg",
        tags=frozenset({"saas", "wiki"}),
    )
    Config = GuruConfig

    def base_url(self) -> str:
        return "https://api.getguru.com/api/v1"

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.username, self.config.api_token)

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(name="collections", path="/collections"),
            StreamSpec(
                name="cards",
                path="/search/query",
                params={"q": self.config.query, "showArchived": "false"},
                paginator=LinkHeaderPagination(size_param="maxResults", page_size=50),
                cursor_field="lastModified",
                client_side_filter=True,
                transform=_with_text,
            ),
        ]


def _with_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["content_text"] = html_to_text(rec.get("content"))
    rec["title"] = rec.get("preferredPhrase") or rec.get("title")
    return rec
