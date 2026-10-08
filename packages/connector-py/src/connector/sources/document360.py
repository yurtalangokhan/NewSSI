"""Document360 source: project versions and their articles (with HTML content)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, StreamSpec
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class Document360Config(BaseModel):
    api_token: str = secret_field(description="API token from Settings > API tokens.")
    base_url: str = Field(
        default="https://apihub.document360.io", description="Use the EU hub URL for EU projects."
    )
    language_code: str = "en"
    timeout_seconds: float = 30.0


class Document360Source(DeclarativeRestSource[Document360Config]):
    definition = ConnectorDefinition(
        name="document360",
        display_name="Document360",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://apidocs.document360.com/",
        icon="document360.svg",
        tags=frozenset({"saas", "docs"}),
    )
    Config = Document360Config

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"api_token": self.config.api_token}

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(name="project_versions", path="/v2/ProjectVersions", records_path="data"),
            StreamSpec(
                name="articles",
                path="/v2/ProjectVersions/{parent[id]}/articles",
                records_path="data",
                params={"langCode": self.config.language_code},
                parent="project_versions",
                parent_field="project_version_id",
                detail_path="/v2/Articles/{record[id]}/" + self.config.language_code,
                detail_records_path="data",
                cursor_field="modified_at",
                client_side_filter=True,
                transform=_with_text,
            ),
        ]


def _with_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["content_text"] = html_to_text(rec.get("html_content")) or rec.get("content")
    return rec
