"""Highspot source: spots and the items (content) inside each spot."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, OffsetPagination, StreamSpec
from ..common.rest_source import basic_auth_header
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = OffsetPagination(limit_param="limit", offset_param="start", page_size=100)


class HighspotConfig(BaseModel):
    key: str = secret_field(description="API key.")
    secret: str = secret_field(description="API secret.")
    base_url: str = Field(default="https://api.highspot.com/v1.0")
    spot_names: list[str] | None = Field(default=None, description="Restrict to these spots.")
    timeout_seconds: float = 60.0


class HighspotSource(DeclarativeRestSource[HighspotConfig]):
    definition = ConnectorDefinition(
        name="highspot",
        display_name="Highspot",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SALES,
        documentation_url="https://spec.highspot.com/",
        icon="highspot.svg",
        tags=frozenset({"saas", "sales-enablement"}),
    )
    Config = HighspotConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.key, self.config.secret)

    def streams(self) -> list[StreamSpec]:
        wanted = set(self.config.spot_names or [])
        return [
            StreamSpec(
                name="spots",
                path="/spots",
                records_path="collection",
                params={"right": "view"},
                paginator=_PAGER,
                transform=(lambda s: s if not wanted or s.get("title") in wanted else None),
            ),
            StreamSpec(
                name="items",
                path="/items?spot={parent[id]}",
                records_path="collection",
                paginator=_PAGER,
                parent="spots",
                parent_field="spot_id",
                cursor_field="date_updated",
                client_side_filter=True,
            ),
        ]
