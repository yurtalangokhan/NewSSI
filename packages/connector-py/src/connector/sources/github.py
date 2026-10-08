"""GitHub source (github.com or Enterprise Server): repositories, issues, pull requests.

Repositories come from an organization (or user) listing, or from an explicit
``repositories`` list. The issues endpoint also returns pull requests; those are
dropped there and served by the ``pull_requests`` stream instead, so a first sync
pays one request per 100 pull requests listed (oldest ``updated_at`` first) before
the first issue; on a large, pull-request-heavy repository that alone exhausts the
anonymous quota of 60 requests per hour. Cursors are tracked per repository.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    LinkHeaderPagination,
    StreamSpec,
    as_iso_z,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = LinkHeaderPagination(size_param="per_page", page_size=100)


class GitHubConfig(BaseModel):
    token: str | None = secret_field(
        default=None,
        description="Personal access token or GitHub App installation token. Empty: anonymous "
        "access to public repositories (60 requests per hour).",
    )
    organization: str | None = Field(default=None, description="Read every repository of this org.")
    user: str | None = Field(default=None, description="Or every repository of this user.")
    repositories: list[str] | None = Field(
        default=None, description="Or exactly these 'owner/repo'."
    )
    base_url: str = Field(default="https://api.github.com", description="GHES: https://host/api/v3")
    include_archived: bool = False
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _scope(self) -> GitHubConfig:
        if not (self.organization or self.user or self.repositories):
            raise ValueError("one of organization, user or repositories is required")
        return self


class GitHubSource(DeclarativeRestSource[GitHubConfig]):
    definition = ConnectorDefinition(
        name="github",
        display_name="GitHub",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.CODE_REPOSITORY,
        documentation_url="https://docs.github.com/en/rest",
        icon="github.svg",
        tags=frozenset({"saas", "devops", "git"}),
    )
    Config = GitHubConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def streams(self) -> list[StreamSpec]:
        c = self.config
        if c.repositories:
            listing = f"/repos/{c.repositories[0]}"
        elif c.organization:
            listing = f"/orgs/{c.organization}/repos"
        else:
            listing = f"/users/{c.user}/repos"

        def keep(repo: dict[str, Any]) -> dict[str, Any] | None:
            return repo if c.include_archived or not repo.get("archived") else None

        def per_repo(name: str, path: str, direction: str = "asc", **kw: Any) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/repos/{{parent[full_name]}}/{path}",
                params={"state": "all", "sort": "updated", "direction": direction},
                paginator=_PAGER,
                parent="repositories",
                parent_key="full_name",
                parent_field="repository",
                per_parent_cursor=True,
                cursor_field="updated_at",
                **kw,
            )

        return [
            StreamSpec(
                name="repositories",
                path=listing,
                params={"type": "all"} if not c.repositories else {},
                paginator=_PAGER,
                cursor_field="updated_at",
                client_side_filter=True,
                transform=keep,
            ),
            per_repo(
                "issues",
                "issues",
                incremental_param="since",
                cursor_format=as_iso_z,
                transform=lambda i: None if "pull_request" in i else i,
            ),
            # No ``since`` for pulls: newest first and stop at the first page already seen.
            per_repo(
                "pull_requests",
                "pulls",
                direction="desc",
                client_side_filter=True,
                stop_when_page_seen=True,
            ),
        ]

    async def _read_records(self, spec: StreamSpec, cursor: Any) -> AsyncIterator[dict[str, Any]]:
        if spec.name != "repositories" or not self.config.repositories:
            async for rec in super()._read_records(spec, cursor):
                yield rec
            return
        for full_name in self.config.repositories:
            repo = await self.get_json(f"/repos/{full_name}")
            if repo and (spec.transform is None or spec.transform(repo) is not None):
                yield repo
