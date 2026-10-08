"""ClickUp source: spaces and tasks of a workspace (team).

``date_updated`` is an epoch-millisecond string; it is both the cursor and the
value sent back as ``date_updated_gt``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    PageNumberPagination,
    StreamSpec,
    as_epoch_millis,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class ClickUpConfig(BaseModel):
    api_token: str = secret_field(description="Personal API token (pk_...).")
    team_id: str = Field(description="Workspace (team) id.")
    include_closed: bool = True
    timeout_seconds: float = 60.0


class ClickUpSource(DeclarativeRestSource[ClickUpConfig]):
    definition = ConnectorDefinition(
        name="clickup",
        display_name="ClickUp",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developer.clickup.com/reference",
        icon="clickup.svg",
        tags=frozenset({"saas", "tasks", "projects"}),
    )
    Config = ClickUpConfig

    def base_url(self) -> str:
        return "https://api.clickup.com/api/v2"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": self.config.api_token}

    def streams(self) -> list[StreamSpec]:
        team = self.config.team_id
        return [
            StreamSpec(name="spaces", path=f"/team/{team}/space", records_path="spaces"),
            StreamSpec(
                name="tasks",
                path=f"/team/{team}/task",
                records_path="tasks",
                params={
                    "include_closed": "true" if self.config.include_closed else "false",
                    "subtasks": "true",
                    "order_by": "updated",
                    "reverse": "true",
                    "include_markdown_description": "true",
                },
                paginator=PageNumberPagination(
                    page_param="page", size_param=None, first_page=0, last_page_path="last_page"
                ),
                cursor_field="date_updated",
                incremental_param="date_updated_gt",
                cursor_format=as_epoch_millis,
            ),
        ]
