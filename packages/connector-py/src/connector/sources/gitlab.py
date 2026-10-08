"""GitLab source (gitlab.com or self-managed) over the REST v4 API.

Streams:

* ``projects``        – projects of a group (recursive) or an explicit list
* ``issues``          – per project, incremental via ``updated_after``
* ``merge_requests``  – per project, incremental via ``updated_after``
* ``wiki_pages``      – per project, full refresh (the API has no cursor)

Auth: personal / group / project access token in the ``PRIVATE-TOKEN`` header;
without one, public projects are read anonymously.
Paging: ``page``/``per_page`` with the ``x-next-page`` response header.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.cursor import CursorTracker
from ..common.rest_source import RestSource
from ..models import (
    Catalog,
    CheckResult,
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


class GitLabConfig(BaseModel):
    base_url: str = Field(default="https://gitlab.com")
    private_token: str | None = secret_field(
        default=None,
        description="Personal, group or project access token. Empty: anonymous access to "
        "public projects.",
    )
    group_id: str | None = Field(
        default=None, description="Group id or URL-encoded path; all projects below are included."
    )
    project_ids: list[str] | None = Field(
        default=None, description="Explicit project ids or URL-encoded paths."
    )
    include_archived: bool = False
    issue_state: str | None = Field(default=None, description="opened | closed | all (default all)")
    page_size: int = Field(default=100, ge=1, le=100)
    timeout_seconds: float = 30.0
    verify_ssl: bool = True

    @model_validator(mode="after")
    def _one_of(self) -> GitLabConfig:
        if not self.group_id and not self.project_ids:
            raise ValueError("either group_id or project_ids is required")
        return self


class GitLabSource(RestSource[GitLabConfig]):
    definition = ConnectorDefinition(
        name="gitlab",
        display_name="GitLab",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.CODE_REPOSITORY,
        documentation_url="https://docs.gitlab.com/ee/api/rest/",
        icon="gitlab.svg",
        tags=frozenset({"saas", "devops", "git"}),
    )
    Config = GitLabConfig
    check_path: ClassVar[str] = "/api/v4/user"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        if not self.config.private_token:
            return {}
        return {"PRIVATE-TOKEN": self.config.private_token}

    async def check(self) -> CheckResult:
        """With a token, the token's own user; without one (anonymous), the first configured
        project or the group: what a read needs, where ``/user`` answers 401."""
        path = self.check_path
        if not self.config.private_token:
            if self.config.project_ids:
                path = f"/api/v4/projects/{_encode(self.config.project_ids[0])}"
            else:
                path = f"/api/v4/groups/{_encode(self.config.group_id or '')}"
        try:
            await self.request("GET", path)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    # ---- catalog -------------------------------------------------------------------

    async def discover(self) -> Catalog:
        def stream(name: str, props: dict[str, Any], incremental: bool) -> Stream:
            return Stream(
                name=name,
                json_schema={"type": "object", "properties": props},
                supported_sync_modes=[SyncMode.FULL_REFRESH]
                + ([SyncMode.INCREMENTAL] if incremental else []),
                source_defined_cursor=incremental,
                default_cursor_field=["updated_at"] if incremental else [],
                source_defined_primary_key=[["id"]],
            )

        item = {
            "id": {"type": "integer"},
            "iid": {"type": "integer"},
            "project_id": {"type": "integer"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "state": {"type": "string"},
            "labels": {"type": "array"},
            "author": {"type": "string"},
            "web_url": {"type": "string"},
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
        }
        return Catalog(
            streams=[
                stream(
                    "projects",
                    {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "path_with_namespace": {"type": "string"},
                        "description": {"type": "string"},
                        "web_url": {"type": "string"},
                        "default_branch": {"type": "string"},
                        "archived": {"type": "boolean"},
                        "last_activity_at": {"type": "string", "format": "date-time"},
                    },
                    False,
                ),
                stream("issues", item, True),
                stream("merge_requests", {**item, "source_branch": {"type": "string"}}, True),
                stream(
                    "wiki_pages",
                    {
                        "project_id": {"type": "integer"},
                        "slug": {"type": "string"},
                        "title": {"type": "string"},
                        "format": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    False,
                ),
            ]
        )

    # ---- read ------------------------------------------------------------------------

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        wanted = set(catalog.names())
        projects = [p async for p in self._projects()]
        if "projects" in wanted:
            for p in projects:
                yield Record(stream="projects", data=p)
        for name, path in (("issues", "issues"), ("merge_requests", "merge_requests")):
            if name not in wanted:
                continue
            configured = next(s for s in catalog.streams if s.stream.name == name)
            tracker = CursorTracker(
                name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
            )
            for p in projects:
                params: dict[str, Any] = {"order_by": "updated_at", "sort": "asc"}
                if tracker.start:
                    params["updated_after"] = tracker.start
                if name == "issues" and self.config.issue_state:
                    params["state"] = self.config.issue_state
                async for raw in self._paginate(f"/api/v4/projects/{p['id']}/{path}", params):
                    item = _item(raw)
                    tracker.observe(item["updated_at"])
                    yield Record(stream=name, data=item)
            if final := tracker.final_state():
                yield final
        if "wiki_pages" in wanted:
            for p in projects:
                if not p.get("wiki_enabled", True):
                    continue
                try:
                    pages = await self.get_json(
                        f"/api/v4/projects/{p['id']}/wikis", params={"with_content": 1}
                    )
                except httpx.HTTPStatusError as exc:
                    # An anonymous project payload carries no ``wiki_enabled``; a disabled or
                    # restricted wiki answers 403 (404 on older servers) and is skipped.
                    if exc.response.status_code in (403, 404):
                        continue
                    raise
                for w in pages or []:
                    yield Record(
                        stream="wiki_pages",
                        data={
                            "project_id": p["id"],
                            "slug": w.get("slug"),
                            "title": w.get("title"),
                            "format": w.get("format"),
                            "content": w.get("content"),
                            "web_url": f"{p['web_url']}/-/wikis/{w.get('slug')}",
                        },
                    )

    async def _projects(self) -> AsyncIterator[dict[str, Any]]:
        if self.config.project_ids:
            for pid in self.config.project_ids:
                raw = await self.get_json(f"/api/v4/projects/{_encode(pid)}")
                yield _project(raw)
            return
        params = {
            "include_subgroups": "true",
            "archived": "true" if self.config.include_archived else "false",
            "simple": "false",
        }
        async for raw in self._paginate(
            f"/api/v4/groups/{_encode(self.config.group_id or '')}/projects", params
        ):
            yield _project(raw)

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        page = 1
        while True:
            resp = await self.request(
                "GET", path, params={**params, "per_page": self.config.page_size, "page": page}
            )
            items = resp.json() if resp.content else []
            for item in items or []:
                yield item
            nxt = resp.headers.get("x-next-page")
            if not nxt or not items:
                return
            page = int(nxt)


def _encode(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value), safe="")


def _project(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "path_with_namespace": raw.get("path_with_namespace"),
        "description": raw.get("description"),
        "web_url": raw.get("web_url"),
        "default_branch": raw.get("default_branch"),
        "archived": raw.get("archived", False),
        "wiki_enabled": raw.get("wiki_enabled", True),
        "last_activity_at": raw.get("last_activity_at"),
    }


def _item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "iid": raw.get("iid"),
        "project_id": raw.get("project_id"),
        "title": raw.get("title"),
        "description": raw.get("description"),
        "state": raw.get("state"),
        "labels": raw.get("labels") or [],
        "author": (raw.get("author") or {}).get("username"),
        "assignees": [a.get("username") for a in raw.get("assignees") or []],
        "milestone": (raw.get("milestone") or {}).get("title"),
        "source_branch": raw.get("source_branch"),
        "target_branch": raw.get("target_branch"),
        "web_url": raw.get("web_url"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }
