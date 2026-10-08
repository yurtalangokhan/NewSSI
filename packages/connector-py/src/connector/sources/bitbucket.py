"""Bitbucket Cloud source: repositories of a workspace, their pull requests and issues.

Repositories without an issue tracker answer 404 on ``/issues``; those are
skipped. Cursors are tracked per repository. Without credentials the public
repositories of the workspace are read anonymously.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    NextUrlPagination,
    PageRequest,
    StreamSpec,
    as_iso,
)
from ..common.rest_source import basic_auth_header
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

PR_STATES = ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]


class BitbucketConfig(BaseModel):
    workspace: str = Field(description="Workspace slug.")
    username: str | None = Field(
        default=None,
        description="With app_password (basic auth). No credentials at all: anonymous access "
        "to the workspace's public repositories.",
    )
    app_password: str | None = secret_field(default=None)
    access_token: str | None = secret_field(default=None, description="Workspace/repo token.")
    repository_slugs: list[str] | None = Field(default=None, description="Restrict to these.")
    base_url: str = "https://api.bitbucket.org/2.0"
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _credentials(self) -> BitbucketConfig:
        if bool(self.username) != bool(self.app_password):
            raise ValueError("username and app_password go together")
        return self


class BitbucketSource(DeclarativeRestSource[BitbucketConfig]):
    definition = ConnectorDefinition(
        name="bitbucket",
        display_name="Bitbucket",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.CODE_REPOSITORY,
        documentation_url="https://developer.atlassian.com/cloud/bitbucket/rest/",
        icon="bitbucket.svg",
        tags=frozenset({"saas", "atlassian", "devops", "git"}),
    )
    Config = BitbucketConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        if self.config.access_token:
            return {"Authorization": f"Bearer {self.config.access_token}"}
        if self.config.username and self.config.app_password:
            return basic_auth_header(self.config.username, self.config.app_password)
        return {}

    def streams(self) -> list[StreamSpec]:
        wanted = set(self.config.repository_slugs or [])

        def updated_after(req: PageRequest, cursor: Any) -> None:
            if cursor is not None:
                req.params["q"] = f'updated_on > "{as_iso(cursor)}"'

        def per_repo(name: str, path: str, params: dict[str, Any], size: int) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/repositories/{{parent[full_name]}}/{path}",
                records_path="values",
                params={**params, "sort": "updated_on"},
                paginator=NextUrlPagination(
                    next_url_path="next", size_param="pagelen", page_size=size
                ),
                parent="repositories",
                parent_key="full_name",
                parent_field="repository",
                per_parent_cursor=True,
                cursor_field="updated_on",
                on_request=updated_after,
            )

        return [
            StreamSpec(
                name="repositories",
                path=f"/repositories/{self.config.workspace}",
                records_path="values",
                paginator=NextUrlPagination(
                    next_url_path="next", size_param="pagelen", page_size=100
                ),
                primary_key=("uuid",),
                cursor_field="updated_on",
                client_side_filter=True,
                transform=(lambda r: r if not wanted or r.get("slug") in wanted else None),
            ),
            per_repo("pull_requests", "pullrequests", {"state": PR_STATES}, 50),
            per_repo("issues", "issues", {}, 100),
        ]
