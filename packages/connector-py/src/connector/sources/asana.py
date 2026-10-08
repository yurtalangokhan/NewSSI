"""Asana source: projects and their tasks (incremental via ``modified_since``)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec, as_iso_z
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = CursorPagination(
    cursor_path="next_page.offset", cursor_param="offset", size_param="limit", page_size=100
)
PROJECT_FIELDS = "name,notes,archived,created_at,modified_at,permalink_url,owner.name"
TASK_FIELDS = (
    "name,notes,completed,completed_at,due_on,created_at,modified_at,permalink_url,"
    "assignee.name,assignee.email,tags.name,memberships.section.name,parent.name,custom_fields"
)


class AsanaConfig(BaseModel):
    access_token: str = secret_field(description="Personal access token.")
    workspace_gid: str | None = Field(default=None, description="Required if you have several.")
    project_gids: list[str] | None = Field(default=None, description="Restrict to these projects.")
    include_archived: bool = False
    timeout_seconds: float = 60.0


class AsanaSource(DeclarativeRestSource[AsanaConfig]):
    definition = ConnectorDefinition(
        name="asana",
        display_name="Asana",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developers.asana.com/reference/rest-api-reference",
        icon="asana.svg",
        tags=frozenset({"saas", "tasks", "projects"}),
    )
    Config = AsanaConfig

    def base_url(self) -> str:
        return "https://app.asana.com/api/1.0"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def streams(self) -> list[StreamSpec]:
        wanted = set(self.config.project_gids or [])
        return [
            StreamSpec(
                name="projects",
                path="/projects",
                records_path="data",
                params={
                    "workspace": self.config.workspace_gid,
                    "archived": None if self.config.include_archived else "false",
                    "opt_fields": PROJECT_FIELDS,
                },
                paginator=_PAGER,
                primary_key=("gid",),
                cursor_field="modified_at",
                client_side_filter=True,
                transform=(lambda r: r if not wanted or r.get("gid") in wanted else None),
            ),
            StreamSpec(
                name="tasks",
                path="/tasks?project={parent[gid]}",
                records_path="data",
                params={"opt_fields": TASK_FIELDS},
                paginator=_PAGER,
                primary_key=("gid",),
                parent="projects",
                parent_key="gid",
                parent_field="project_gid",
                per_parent_cursor=True,
                cursor_field="modified_at",
                incremental_param="modified_since",
                cursor_format=as_iso_z,
            ),
        ]
