"""Loopio source: library entries (question / answer pairs) via OAuth2 client credentials."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, PageNumberPagination, StreamSpec
from ..common.oauth2 import OAuth2BearerMixin, OAuth2Token
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class LoopioConfig(BaseModel):
    client_id: str = Field(description="OAuth2 client id.")
    client_secret: str = secret_field()
    base_url: str = Field(
        default="https://api.loopio.com", description="Use the EU/AU host if needed."
    )
    stack_name: str | None = Field(default=None, description="Restrict to one stack.")
    timeout_seconds: float = 60.0


class LoopioSource(OAuth2BearerMixin, DeclarativeRestSource[LoopioConfig]):
    definition = ConnectorDefinition(
        name="loopio",
        display_name="Loopio",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://developer.loopio.com/",
        icon="loopio.svg",
        tags=frozenset({"saas", "rfp"}),
    )
    Config = LoopioConfig

    def base_url(self) -> str:
        return self.config.base_url

    def oauth2_token(self) -> OAuth2Token:
        return OAuth2Token(
            f"{self.config.base_url.rstrip('/')}/oauth2/access_token",
            {
                "grant_type": "client_credentials",
                "scope": "library:read",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
        )

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="library_entries",
                path="/data/v2/libraryEntries",
                records_path="items",
                params={"inlineStyles": "false"},
                paginator=PageNumberPagination(
                    page_param="page",
                    size_param="pageSize",
                    page_size=100,
                    last_page_path="totalPages",
                ),
                cursor_field="lastUpdatedDate",
                client_side_filter=True,
                transform=self._transform,
            )
        ]

    def _transform(self, rec: dict[str, Any]) -> dict[str, Any] | None:
        stack = ((rec.get("location") or {}).get("stack") or {}).get("name")
        if self.config.stack_name and stack != self.config.stack_name:
            return None
        rec["questions_text"] = [html_to_text(q.get("text")) for q in rec.get("questions") or []]
        rec["answer_text"] = html_to_text((rec.get("answer") or {}).get("text"))
        return rec
