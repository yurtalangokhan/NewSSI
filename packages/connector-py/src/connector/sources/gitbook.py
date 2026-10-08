"""GitBook source: spaces of an organization and their pages (markdown body).

The content endpoint returns the page *tree*; it is flattened so every page and
sub-page becomes a record, then each page is fetched once for its markdown.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class GitBookConfig(BaseModel):
    api_token: str = secret_field(description="Personal access token.")
    organization_id: str = Field(description="Organization whose spaces are read.")
    base_url: str = "https://api.gitbook.com"
    timeout_seconds: float = 30.0


class GitBookSource(DeclarativeRestSource[GitBookConfig]):
    definition = ConnectorDefinition(
        name="gitbook",
        display_name="GitBook",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://developer.gitbook.com/",
        icon="gitbook.svg",
        tags=frozenset({"saas", "docs"}),
    )
    Config = GitBookConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="spaces",
                path=f"/v1/orgs/{self.config.organization_id}/spaces",
                records_path="items",
                paginator=CursorPagination(
                    cursor_path="next.page", cursor_param="page", size_param="limit", page_size=100
                ),
                cursor_field="updatedAt",
                client_side_filter=True,
            ),
            StreamSpec(
                name="pages",
                path="/v1/spaces/{parent[id]}/content",
                records_path=None,
                parent="spaces",
                parent_field="space_id",
                expand=_flatten_tree,
                detail_path="/v1/spaces/{parent[id]}/content/page/{record[id]}",
                detail_params={"format": "markdown"},
                cursor_field="updatedAt",
                client_side_filter=True,
            ),
        ]


def _flatten_tree(revision: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def walk(nodes: list[dict[str, Any]], trail: list[str]) -> Iterator[dict[str, Any]]:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            children = node.get("pages") or []
            page = {k: v for k, v in node.items() if k != "pages"}
            page["breadcrumb"] = [*trail, node.get("title", "")]
            if node.get("type", "document") == "document":
                yield page
            yield from walk(children, page["breadcrumb"])

    yield from walk(revision.get("pages") or [], [])
