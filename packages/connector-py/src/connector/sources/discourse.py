"""Discourse source: categories, topics and posts.

``topics`` pages through ``/latest.json`` by activity, newest first, and an
incremental run stops at the first page it has already seen. ``posts`` walks
``/posts.json`` backwards with ``before=<id>`` (newest *created* first), so
incremental sync filters client-side on ``updated_at`` and has to walk the
whole list: the order is the post id, and an old post edited since the last
run sits anywhere in it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    LastRecordPagination,
    PageNumberPagination,
    StreamSpec,
)
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class DiscourseConfig(BaseModel):
    base_url: str = Field(description="e.g. https://forum.acme.com")
    api_key: str | None = secret_field(
        default=None, description="API key. Empty: the anonymous view of a public forum."
    )
    api_username: str = Field(default="system", description="User the API key acts as.")
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class DiscourseSource(DeclarativeRestSource[DiscourseConfig]):
    definition = ConnectorDefinition(
        name="discourse",
        display_name="Discourse",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://docs.discourse.org/",
        icon="discourse.svg",
        tags=frozenset({"forum", "community"}),
    )
    Config = DiscourseConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        if not self.config.api_key:
            return {}
        return {"Api-Key": self.config.api_key, "Api-Username": self.config.api_username}

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="categories",
                path="/categories.json",
                records_path="category_list.categories",
            ),
            StreamSpec(
                name="topics",
                path="/latest.json",
                records_path="topic_list.topics",
                params={"order": "activity", "ascending": "false"},
                paginator=PageNumberPagination(
                    page_param="page",
                    size_param=None,
                    first_page=0,
                    has_more_path="topic_list.more_topics_url",
                ),
                cursor_field="bumped_at",
                client_side_filter=True,
                stop_when_page_seen=True,
            ),
            StreamSpec(
                name="posts",
                path="/posts.json",
                records_path="latest_posts",
                paginator=LastRecordPagination(param="before", record_field="id", size_param=None),
                cursor_field="updated_at",
                client_side_filter=True,
                transform=_with_text,
            ),
        ]


def _with_text(rec: dict[str, Any]) -> dict[str, Any]:
    rec["text"] = rec.get("raw") or html_to_text(rec.get("cooked"))
    return rec
