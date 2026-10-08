"""Linear source (GraphQL): teams, projects and issues with their comments."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.cursor import CursorTracker
from ..common.declarative import as_iso
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

ISSUES = """
query($after: String, $filter: IssueFilter) {
  issues(first: 50, after: $after, filter: $filter, orderBy: updatedAt) {
    nodes {
      id identifier title description url priority estimate createdAt updatedAt completedAt
      state { name type } assignee { name email } creator { name email }
      team { id key name } project { id name } labels { nodes { name } }
      comments { nodes { id body createdAt user { name } } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""
PROJECTS = """
query($after: String, $filter: ProjectFilter) {
  projects(first: 50, after: $after, filter: $filter) {
    nodes { id name description url state createdAt updatedAt lead { name } }
    pageInfo { hasNextPage endCursor }
  }
}
"""
TEAMS = """
query($after: String) {
  teams(first: 100, after: $after) {
    nodes { id key name description createdAt updatedAt }
    pageInfo { hasNextPage endCursor }
  }
}
"""
_STREAMS: dict[str, tuple[str, bool]] = {
    "teams": (TEAMS, False),
    "projects": (PROJECTS, True),
    "issues": (ISSUES, True),
}


class LinearConfig(BaseModel):
    api_key: str = secret_field(description="Personal API key (lin_api_...).")
    team_keys: list[str] | None = Field(default=None, description="Restrict issues to teams.")
    timeout_seconds: float = 60.0


class LinearSource(GraphQLSource[LinearConfig]):
    definition = ConnectorDefinition(
        name="linear",
        display_name="Linear",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developers.linear.app/docs/graphql/working-with-the-graphql-api",
        icon="linear.svg",
        tags=frozenset({"saas", "issues"}),
    )
    Config = LinearConfig
    check_query: ClassVar[str] = "query { viewer { id } }"

    def base_url(self) -> str:
        return "https://api.linear.app"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": self.config.api_key}

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name=name,
                    supported_sync_modes=[SyncMode.FULL_REFRESH]
                    + ([SyncMode.INCREMENTAL] if incremental else []),
                    source_defined_cursor=incremental,
                    default_cursor_field=["updatedAt"] if incremental else [],
                    source_defined_primary_key=[["id"]],
                )
                for name, (_, incremental) in _STREAMS.items()
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        for configured in catalog.streams:
            name = configured.stream.name
            if name not in _STREAMS:
                continue
            query, can_filter = _STREAMS[name]
            tracker = CursorTracker(
                name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL and can_filter
            )
            variables: dict[str, Any] = {}
            if can_filter:
                flt: dict[str, Any] = {}
                if tracker.start:
                    flt["updatedAt"] = {"gt": as_iso(tracker.start)}
                if name == "issues" and self.config.team_keys:
                    flt["team"] = {"key": {"in": self.config.team_keys}}
                variables["filter"] = flt or None
            async for node in self.connection(query, name, variables):
                tracker.observe(node.get("updatedAt"))
                yield Record(stream=name, data=_flatten(node))
            if final := tracker.final_state():
                yield final


def _flatten(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("labels", "comments"):
        if isinstance(node.get(key), dict):
            node[key] = node[key].get("nodes") or []
    return node
