"""Axero (Communifire) source: articles, blogs and wiki pages, plus spaces.

Content comes from ``/api/content/list`` filtered by ``EntityType``
(3 = article, 4 = blog, 9 = wiki), optionally restricted to a list of spaces.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, PageNumberPagination, StreamSpec
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

ENTITY_TYPES = {"articles": 3, "blogs": 4, "wikis": 9}
_PAGER = PageNumberPagination(page_param="StartPage", size_param=None, first_page=1)


class AxeroConfig(BaseModel):
    base_url: str = Field(description="e.g. https://acme.axerosolutions.com")
    api_key: str = secret_field(description="REST API key.")
    space_ids: list[int] | None = Field(default=None, description="Restrict to these spaces.")
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class AxeroSource(DeclarativeRestSource[AxeroConfig]):
    definition = ConnectorDefinition(
        name="axero",
        display_name="Axero",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://my.axerosolutions.com/spaces/5/communifire-documentation",
        icon="axero.svg",
        tags=frozenset({"saas", "intranet"}),
    )
    Config = AxeroConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Rest-Api-Key": self.config.api_key}

    def streams(self) -> list[StreamSpec]:
        spaces = ",".join(str(s) for s in self.config.space_ids or []) or None
        specs = [
            StreamSpec(
                name="spaces",
                path="/api/spaces",
                records_path="ResponseData",
                primary_key=("SpaceID",),
            )
        ]
        for name, entity_type in ENTITY_TYPES.items():
            specs.append(
                StreamSpec(
                    name=name,
                    path="/api/content/list",
                    records_path="ResponseData",
                    params={
                        "EntityType": entity_type,
                        "SortColumn": "DateUpdated",
                        "SortOrder": 0,
                        "SpaceID": spaces,
                    },
                    paginator=_PAGER,
                    primary_key=("ContentID",),
                    cursor_field="DateUpdated",
                    client_side_filter=True,
                    transform=_with_text,
                )
            )
        return specs


def _with_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["content_text"] = html_to_text(rec.get("ContentBody"))
    return rec
