"""Coda source: docs and, per doc, pages and tables."""

from __future__ import annotations

from pydantic import BaseModel

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = CursorPagination(
    cursor_path="nextPageToken", cursor_param="pageToken", size_param="limit", page_size=100
)


class CodaConfig(BaseModel):
    api_token: str = secret_field(description="Coda API token.")
    timeout_seconds: float = 30.0


class CodaSource(DeclarativeRestSource[CodaConfig]):
    definition = ConnectorDefinition(
        name="coda",
        display_name="Coda",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://coda.io/developers/apis/v1",
        icon="coda.svg",
        tags=frozenset({"saas", "docs"}),
    )
    Config = CodaConfig

    def base_url(self) -> str:
        return "https://coda.io/apis/v1"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def streams(self) -> list[StreamSpec]:
        def per_doc(name: str) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/docs/{{parent[id]}}/{name}",
                records_path="items",
                paginator=_PAGER,
                parent="docs",
                parent_field="doc_id",
            )

        return [
            StreamSpec(
                name="docs",
                path="/docs",
                records_path="items",
                paginator=_PAGER,
                cursor_field="updatedAt",
                client_side_filter=True,
            ),
            per_doc("pages"),
            per_doc("tables"),
        ]
