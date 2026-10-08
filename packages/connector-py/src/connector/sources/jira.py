"""Jira source (Cloud and Data Center).

Streams:

* ``projects`` – project metadata
* ``issues``   – issues with a configurable field list; comments are inlined
                 when ``comment`` is among the fields

Incremental sync for ``issues`` uses JQL ``updated >=`` ordered by ``updated``.
Cloud uses ``/rest/api/3/search/jql`` (``nextPageToken`` paging); Data Center
uses ``/rest/api/2/search`` (``startAt`` paging). Pick with ``deployment``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, tzinfo
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.atlassian_auth import atlassian_auth_headers, user_time_zone
from ..common.cursor import CursorTracker
from ..common.rest_source import RestSource, parse_iso
from ..common.rest_source import iso_or_none as _iso
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

DEFAULT_FIELDS = [
    "summary",
    "description",
    "status",
    "issuetype",
    "priority",
    "project",
    "assignee",
    "reporter",
    "labels",
    "components",
    "created",
    "updated",
    "resolutiondate",
    "comment",
]


class JiraConfig(BaseModel):
    base_url: str = Field(description="e.g. https://acme.atlassian.net or https://jira.acme.com")
    deployment: Literal["cloud", "server"] = "cloud"
    auth_type: Literal["basic", "bearer"] = Field(
        default="basic",
        description="basic = e-mail + API token (Cloud); bearer = PAT (Data Center).",
    )
    email: str | None = None
    api_token: str | None = secret_field(default=None, description="API token or PAT.")
    project_keys: list[str] | None = Field(default=None, description="Restrict to these projects.")
    jql_filter: str | None = Field(default=None, description="Extra JQL AND-ed into the query.")
    fields: list[str] = Field(default_factory=lambda: list(DEFAULT_FIELDS))
    render_fields: bool = Field(
        default=False, description="Also fetch HTML-rendered fields (renderedFields)."
    )
    page_size: int = Field(default=100, ge=1, le=1000)
    timezone: str | None = Field(
        default=None,
        description="IANA zone JQL dates are rendered in. Default: the API user's profile "
        "zone (Jira reads JQL dates in it), UTC when the profile has none.",
    )
    timeout_seconds: float = 30.0
    verify_ssl: bool = True


class JiraSource(RestSource[JiraConfig]):
    definition = ConnectorDefinition(
        name="jira",
        display_name="Jira",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.TICKETING,
        documentation_url="https://developer.atlassian.com/cloud/jira/platform/rest/v3/",
        icon="jira.svg",
        tags=frozenset({"saas", "atlassian", "issues"}),
    )
    Config = JiraConfig
    check_path: ClassVar[str] = "/rest/api/2/myself"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return atlassian_auth_headers(
            self.config.auth_type, self.config.email, self.config.api_token
        )

    async def check(self) -> CheckResult:
        """With a token, the token's own user; without one (anonymous), the project list:
        what a read needs, where ``/myself`` answers 401."""
        path = self.check_path
        params: dict[str, Any] | None = None
        if not self.config.api_token:
            if self.config.deployment == "cloud":
                path, params = f"{self._api}/project/search", {"maxResults": 1}
            else:
                path = f"{self._api}/project"
        try:
            await self.request("GET", path, params=params)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    @property
    def _api(self) -> str:
        return "/rest/api/3" if self.config.deployment == "cloud" else "/rest/api/2"

    # ---- catalog -------------------------------------------------------------------

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="projects",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "key": {"type": "string"},
                            "name": {"type": "string"},
                            "project_type": {"type": "string"},
                            "lead": {"type": "string"},
                        },
                    },
                    source_defined_primary_key=[["key"]],
                ),
                Stream(
                    name="issues",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "key": {"type": "string"},
                            "url": {"type": "string"},
                            "project_key": {"type": "string"},
                            "summary": {"type": "string"},
                            "description": {"type": "string"},
                            "status": {"type": "string"},
                            "issue_type": {"type": "string"},
                            "priority": {"type": "string"},
                            "assignee": {"type": "string"},
                            "reporter": {"type": "string"},
                            "labels": {"type": "array"},
                            "comments": {"type": "array"},
                            "created": {"type": "string", "format": "date-time"},
                            "updated": {"type": "string", "format": "date-time"},
                            "fields": {"type": "object"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["updated"],
                    source_defined_primary_key=[["id"]],
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
        for configured in catalog.streams:
            name = configured.stream.name
            if name == "projects":
                async for p in self._projects():
                    yield Record(stream=name, data=p)
            elif name == "issues":
                tracker = CursorTracker(
                    name, state, enabled=configured.sync_mode is SyncMode.INCREMENTAL
                )
                async for issue in self._issues(tracker.start):
                    tracker.observe(issue["updated"])
                    yield Record(stream=name, data=issue)
                if final := tracker.final_state():
                    yield final

    async def _projects(self) -> AsyncIterator[dict[str, Any]]:
        if self.config.deployment == "cloud":
            params: dict[str, Any] = {"maxResults": self.config.page_size, "startAt": 0}
            if self.config.project_keys:
                params["keys"] = ",".join(self.config.project_keys)
            while True:
                page = await self.get_json(f"{self._api}/project/search", params=params)
                for raw in page.get("values", []) or []:
                    yield _project(raw)
                if page.get("isLast", True) or not page.get("values"):
                    return
                params["startAt"] = int(page.get("startAt", 0)) + len(page["values"])
        else:
            for raw in await self.get_json(f"{self._api}/project") or []:
                if self.config.project_keys and raw.get("key") not in self.config.project_keys:
                    continue
                yield _project(raw)

    def _jql(self, since: str | None, zone: tzinfo = UTC) -> str:
        clauses: list[str] = []
        if self.config.project_keys:
            clauses.append(
                "project in (" + ",".join(f'"{k}"' for k in self.config.project_keys) + ")"
            )
        if self.config.jql_filter:
            clauses.append(f"({self.config.jql_filter})")
        stamp = parse_iso(since) if since else None
        if stamp:
            # Jira reads the literal in the API user's profile zone (see atlassian_auth).
            clauses.append(f'updated > "{stamp.astimezone(zone).strftime("%Y/%m/%d %H:%M")}"')
        return (" AND ".join(clauses) if clauses else "") + " ORDER BY updated ASC"

    async def _issues(self, since: str | None) -> AsyncIterator[dict[str, Any]]:
        zone: tzinfo = UTC
        if since:
            zone = await user_time_zone(self, f"{self._api}/myself", self.config.timezone)
        jql = self._jql(since, zone).strip()
        fields = ",".join(self.config.fields)
        expand = "renderedFields" if self.config.render_fields else None
        if self.config.deployment == "cloud":
            token: str | None = None
            while True:
                params: dict[str, Any] = {
                    "jql": jql,
                    "maxResults": self.config.page_size,
                    "fields": fields,
                }
                if expand:
                    params["expand"] = expand
                if token:
                    params["nextPageToken"] = token
                page = await self.get_json(f"{self._api}/search/jql", params=params)
                for raw in page.get("issues", []) or []:
                    yield self._issue(raw)
                token = page.get("nextPageToken")
                if not token or page.get("isLast"):
                    return
        else:
            start = 0
            while True:
                params = {
                    "jql": jql,
                    "startAt": start,
                    "maxResults": self.config.page_size,
                    "fields": fields,
                }
                if expand:
                    params["expand"] = expand
                page = await self.get_json(f"{self._api}/search", params=params)
                issues = page.get("issues", []) or []
                for raw in issues:
                    yield self._issue(raw)
                start += len(issues)
                if not issues or start >= int(page.get("total", 0)):
                    return

    def _issue(self, raw: dict[str, Any]) -> dict[str, Any]:
        f = raw.get("fields") or {}
        comments = ((f.get("comment") or {}).get("comments") or []) if "comment" in f else []
        rendered = raw.get("renderedFields") or {}
        return {
            "id": str(raw.get("id")),
            "key": raw.get("key"),
            "url": f"{self.config.base_url.rstrip('/')}/browse/{raw.get('key')}",
            "project_key": (f.get("project") or {}).get("key"),
            "summary": f.get("summary"),
            "description": rendered.get("description") or _text(f.get("description")),
            "status": (f.get("status") or {}).get("name"),
            "issue_type": (f.get("issuetype") or {}).get("name"),
            "priority": (f.get("priority") or {}).get("name"),
            "assignee": _person(f.get("assignee")),
            "reporter": _person(f.get("reporter")),
            "labels": f.get("labels") or [],
            "comments": [
                {
                    "id": c.get("id"),
                    "author": _person(c.get("author")),
                    "body": _text(c.get("body")),
                    "created": _iso(c.get("created")),
                }
                for c in comments
            ],
            "created": _iso(f.get("created")),
            "updated": _iso(f.get("updated")),
            "fields": {k: v for k, v in f.items() if k not in {"comment", "description"}},
        }


def _project(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id")),
        "key": raw.get("key"),
        "name": raw.get("name"),
        "project_type": raw.get("projectTypeKey"),
        "lead": _person(raw.get("lead")),
    }


def _person(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("displayName") or value.get("emailAddress") or value.get("name")


def _text(value: Any) -> str | None:
    """Plain text from a Jira description/comment: string (v2) or ADF document (v3)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        _walk_adf(value, parts)
        return "".join(parts).strip()
    return str(value)


def _walk_adf(node: dict[str, Any], out: list[str]) -> None:
    node_type = node.get("type")
    if node_type == "text":
        out.append(node.get("text", ""))
    elif node_type == "hardBreak":
        out.append("\n")
    elif node_type == "mention":
        out.append((node.get("attrs") or {}).get("text", ""))
    for child in node.get("content") or []:
        _walk_adf(child, out)
    if node_type in {"paragraph", "heading", "listItem", "codeBlock", "blockquote"}:
        out.append("\n")
