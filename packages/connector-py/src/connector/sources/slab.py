"""Slab source (GraphQL): posts and topics.

Post bodies are stored as Quill deltas; they are flattened to plain text in
``content_text`` while the original delta is kept under ``content``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.cursor import CursorTracker, is_newer
from ..common.graphql import GraphQLSource
from ..models import (
    Catalog,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)

POSTS_QUERY = """
query { organization { posts {
  id title content insertedAt updatedAt publishedAt archivedAt version
  owner { id name email } topics { id name }
} } }
"""
TOPICS_QUERY = "query { organization { topics { id name description insertedAt updatedAt } } }"


class SlabConfig(BaseModel):
    api_token: str = secret_field(description="Slab API token.")
    base_url: str = Field(default="https://api.slab.com")
    team_url: str | None = Field(
        default=None, description="e.g. https://acme.slab.com, used to build post links."
    )
    timeout_seconds: float = 60.0


class SlabSource(GraphQLSource[SlabConfig]):
    definition = ConnectorDefinition(
        name="slab",
        display_name="Slab",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://studio.apollographql.com/public/Slab/variant/current/home",
        icon="slab.svg",
        tags=frozenset({"saas", "wiki"}),
    )
    Config = SlabConfig
    graphql_path: ClassVar[str] = "/v1/graphql"
    check_query: ClassVar[str] = "query { organization { id } }"

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": self.config.api_token}

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="posts",
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["updatedAt"],
                    source_defined_primary_key=[["id"]],
                ),
                Stream(name="topics", source_defined_primary_key=[["id"]]),
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for configured in catalog.streams:
            name = configured.stream.name
            if name == "topics":
                data = await self.execute(TOPICS_QUERY)
                for topic in (data.get("organization") or {}).get("topics") or []:
                    yield Record(stream=name, data=topic)
            elif name == "posts":
                tracker = CursorTracker(
                    name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
                )
                data = await self.execute(POSTS_QUERY)
                for post in (data.get("organization") or {}).get("posts") or []:
                    if tracker.start is not None and not is_newer(
                        post.get("updatedAt"), tracker.start
                    ):
                        continue
                    tracker.observe(post.get("updatedAt"))
                    post["content_text"] = quill_to_text(post.get("content"))
                    if self.config.team_url:
                        post["url"] = f"{self.config.team_url.rstrip('/')}/posts/{post['id']}"
                    yield Record(stream=name, data=post)
                if final := tracker.final_state():
                    yield final


def quill_to_text(content: Any) -> str:
    """Flatten a Quill delta (JSON string, list of ops or ``{"ops": [...]}``)."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return content
    ops = content.get("ops") if isinstance(content, dict) else content
    if not isinstance(ops, list):
        return ""
    return "".join(op["insert"] for op in ops if isinstance(op.get("insert"), str)).strip()
