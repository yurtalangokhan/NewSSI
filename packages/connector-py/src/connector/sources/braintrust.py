"""Braintrust source: projects, experiments, datasets (+ their rows) and prompts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    CursorPagination,
    DeclarativeRestSource,
    LastRecordPagination,
    StreamSpec,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = LastRecordPagination(
    param="starting_after", record_field="id", size_param="limit", page_size=100
)


class BraintrustConfig(BaseModel):
    api_key: str = secret_field()
    base_url: str = Field(
        default="https://api.braintrust.dev", description="Or your data plane URL."
    )
    project_name: str | None = Field(default=None, description="Restrict to one project.")
    include_dataset_rows: bool = True
    timeout_seconds: float = 60.0


class BraintrustSource(DeclarativeRestSource[BraintrustConfig]):
    definition = ConnectorDefinition(
        name="braintrust",
        display_name="Braintrust",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.OTHER,
        documentation_url="https://www.braintrust.dev/docs/reference/api",
        icon="braintrust.svg",
        tags=frozenset({"saas", "llm", "evaluation"}),
    )
    Config = BraintrustConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def streams(self) -> list[StreamSpec]:
        scope = {"project_name": self.config.project_name}

        def listing(name: str, path: str, *, scoped: bool = True) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/v1/{path}",
                records_path="objects",
                params=scope if scoped else {"project_name": self.config.project_name},
                paginator=_PAGER,
                cursor_field="created",
                client_side_filter=True,
            )

        specs = [
            listing("projects", "project"),
            listing("experiments", "experiment"),
            listing("datasets", "dataset"),
            listing("prompts", "prompt"),
        ]
        if self.config.include_dataset_rows:
            specs.append(
                StreamSpec(
                    name="dataset_rows",
                    path="/v1/dataset/{parent[id]}/fetch",
                    records_path="events",
                    paginator=CursorPagination(
                        cursor_path="cursor",
                        cursor_param="cursor",
                        size_param="limit",
                        page_size=500,
                    ),
                    parent="datasets",
                    parent_field="dataset_id",
                )
            )
        return specs
