"""Outline source: collections and documents (markdown text included by the API)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, OffsetPagination, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = OffsetPagination(page_size=100, in_body=True)


class OutlineConfig(BaseModel):
    base_url: str = Field(default="https://app.getoutline.com", description="Cloud or self-hosted.")
    api_token: str = secret_field(description="API token (ol_api_...).")
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class OutlineSource(DeclarativeRestSource[OutlineConfig]):
    definition = ConnectorDefinition(
        name="outline",
        display_name="Outline",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://www.getoutline.com/developers",
        icon="outline.svg",
        tags=frozenset({"wiki", "self-hosted"}),
    )
    Config = OutlineConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="collections",
                path="/api/collections.list",
                method="POST",
                body={},
                records_path="data",
                paginator=_PAGER,
            ),
            StreamSpec(
                name="documents",
                path="/api/documents.list",
                method="POST",
                body={"sort": "updatedAt", "direction": "ASC"},
                records_path="data",
                paginator=_PAGER,
                cursor_field="updatedAt",
                client_side_filter=True,
            ),
        ]
