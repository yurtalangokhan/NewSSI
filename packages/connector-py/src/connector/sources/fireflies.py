"""Fireflies.ai source (GraphQL): meeting transcripts with summary and full text.

The ``transcripts`` query pages with ``limit`` / ``skip`` rather than a Relay
connection, and filters by ``fromDate`` for incremental sync.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.cursor import CursorTracker
from ..common.declarative import as_iso_z, from_epoch_millis
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

TRANSCRIPTS = """
query($limit: Int, $skip: Int, $fromDate: DateTime) {
  transcripts(limit: $limit, skip: $skip, fromDate: $fromDate) {
    id title date duration transcript_url organizer_email participants
    summary { overview action_items keywords }
    sentences { speaker_name text }
  }
}
"""


class FirefliesConfig(BaseModel):
    api_key: str = secret_field()
    page_size: int = Field(default=25, ge=1, le=50)
    timeout_seconds: float = 120.0


class FirefliesSource(GraphQLSource[FirefliesConfig]):
    definition = ConnectorDefinition(
        name="fireflies",
        display_name="Fireflies.ai",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SALES,
        documentation_url="https://docs.fireflies.ai/",
        icon="fireflies.svg",
        tags=frozenset({"saas", "meetings", "transcripts"}),
    )
    Config = FirefliesConfig
    check_query: ClassVar[str] = "query { user { user_id } }"

    def base_url(self) -> str:
        return "https://api.fireflies.ai"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="transcripts",
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["date_iso"],
                    source_defined_primary_key=[["id"]],
                )
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        configured = next((s for s in catalog.streams if s.stream.name == "transcripts"), None)
        if configured is None:
            return
        tracker = CursorTracker(
            "transcripts", state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
        )
        skip, size = 0, self.config.page_size
        while True:
            variables: dict[str, Any] = {"limit": size, "skip": skip}
            if tracker.start:
                variables["fromDate"] = as_iso_z(tracker.start)
            data = await self.execute(TRANSCRIPTS, variables)
            batch = data.get("transcripts") or []
            for item in batch:
                item["date_iso"] = from_epoch_millis(item.get("date"))
                item["text"] = "\n".join(
                    f"{s.get('speaker_name') or ''}: {s.get('text') or ''}".lstrip(": ")
                    for s in item.get("sentences") or []
                )
                tracker.observe(item["date_iso"])
                yield Record(stream="transcripts", data=item)
            if len(batch) < size:
                break
            skip += size
        if final := tracker.final_state():
            yield final
