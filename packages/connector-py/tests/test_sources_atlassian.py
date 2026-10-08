"""Confluence and Jira sources against a fake Atlassian API (httpx MockTransport)."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from connector import Catalog, ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.sources.confluence import ConfluenceSource
from connector.sources.jira import JiraSource


def _client(handler, base: str) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=base)


# ---------------------------------------------------------------------------
# Confluence
# ---------------------------------------------------------------------------

PAGES = [
    {
        "id": "101",
        "type": "page",
        "status": "current",
        "title": "Onboarding",
        "space": {"key": "HR"},
        "body": {"storage": {"value": "<p>Welcome</p>"}},
        "version": {"number": 3, "when": "2026-01-01T10:00:00.000Z", "by": {"displayName": "Ann"}},
        "metadata": {"labels": {"results": [{"name": "guide"}]}},
        "ancestors": [{"title": "HR Home"}],
        "_links": {"webui": "/spaces/HR/pages/101"},
    },
    {
        "id": "102",
        "type": "page",
        "status": "current",
        "title": "Benefits",
        "space": {"key": "HR"},
        "body": {"storage": {"value": "<p>Perks</p>"}},
        "version": {"number": 1, "when": "2026-01-03T10:00:00.000Z", "by": {"displayName": "Bob"}},
        "_links": {"webui": "/spaces/HR/pages/102"},
    },
]


def _confluence_handler(seen: list[httpx.Request]):  # noqa: ANN202
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/wiki/rest/api/space":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "key": "HR", "name": "Human Resources", "type": "global"}
                    ],
                    "size": 1,
                    "limit": 50,
                    "_links": {},
                },
            )
        if path == "/wiki/rest/api/content/search":
            cql = request.url.params["cql"]
            start = int(request.url.params.get("start", 0))
            pages = PAGES
            if "lastmodified >" in cql:
                pages = [p for p in PAGES if p["version"]["when"] > "2026-01-02"]
            # one item per page to exercise paging
            chunk = pages[start : start + 1]
            has_next = start + 1 < len(pages)
            return httpx.Response(
                200,
                json={
                    "results": chunk,
                    "start": start,
                    "size": len(chunk),
                    "limit": 1,
                    "_links": {"next": "/x"} if has_next else {},
                },
            )
        return httpx.Response(404)

    return handler


async def test_confluence_full_refresh_and_auth() -> None:
    seen: list[httpx.Request] = []
    cfg = ConfluenceSource.validate_config(
        {
            "base_url": "https://acme.atlassian.net/wiki",
            "email": "me@acme.com",
            "api_token": "tok",
            "space_keys": ["HR"],
            "page_size": 1,
        }
    )
    src = ConfluenceSource(cfg, client=_client(_confluence_handler(seen), cfg.base_url))
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["spaces", "pages", "blogposts"]

    items = [
        i async for i in src.read(ConfiguredCatalog.from_catalog(catalog, only=["spaces", "pages"]))
    ]
    records = [i for i in items if isinstance(i, Record)]
    assert [r.stream for r in records] == ["spaces", "pages", "pages"]
    page = records[1].data
    assert page["title"] == "Onboarding" and page["body_html"] == "<p>Welcome</p>"
    assert page["labels"] == ["guide"] and page["ancestors"] == ["HR Home"]
    assert page["url"] == "https://acme.atlassian.net/wiki/spaces/HR/pages/101"
    assert page["updated_at"] == "2026-01-01T10:00:00+00:00"
    assert not any(isinstance(i, State) for i in items)

    expected = "Basic " + base64.b64encode(b"me@acme.com:tok").decode()
    assert all(r.headers["Authorization"] == expected for r in seen)
    cql = next(r for r in seen if r.url.path.endswith("/search")).url.params["cql"]
    assert cql == 'type=page and space in ("HR") order by lastmodified asc'


async def test_confluence_incremental_uses_cql_and_emits_state() -> None:
    seen: list[httpx.Request] = []
    cfg = ConfluenceSource.validate_config(
        {"base_url": "https://acme.atlassian.net/wiki", "auth_type": "bearer", "api_token": "pat"}
    )
    src = ConfluenceSource(cfg, client=_client(_confluence_handler(seen), cfg.base_url))
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["pages"]
    )
    prior = SyncState(streams={"pages": {"cursor": "2026-01-02T00:00:00+00:00"}})
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["id"] for i in items if isinstance(i, Record)] == ["102"]
    assert items[-1] == State(stream="pages", data={"cursor": "2026-01-03T10:00:00+00:00"})
    cql = seen[-1].url.params["cql"]
    assert 'lastmodified > "2026-01-02 00:00"' in cql
    assert seen[-1].headers["Authorization"] == "Bearer pat"


async def test_confluence_follows_next_links_on_short_pages() -> None:
    # Permission filtering makes Confluence return fewer results than ``limit`` while more
    # pages remain: ``_links.next`` decides, not the page size.
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/wiki/rest/api/content/search":
            start = int(request.url.params.get("start", 0))
            page = {
                "results": [PAGES[0]],
                "start": 0,
                "size": 1,
                "limit": 25,
                "_links": {"next": "/x"},
            }
            if start:
                page = {"results": [PAGES[1]], "start": start, "size": 1, "limit": 25, "_links": {}}
            return httpx.Response(200, json=page)
        return httpx.Response(404)

    cfg = ConfluenceSource.validate_config(
        {"base_url": "https://acme.atlassian.net/wiki", "auth_type": "bearer", "api_token": "p"}
    )
    src = ConfluenceSource(cfg, client=_client(handler, cfg.base_url))
    catalog = Catalog(streams=[(await src.discover()).get("pages")])
    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [i.data["id"] for i in items] == ["101", "102"]
    assert [r.url.params.get("start") for r in seen if r.url.path.endswith("/search")] == ["0", "1"]


async def test_confluence_renders_cql_dates_in_the_api_users_time_zone() -> None:
    # CQL date literals are read in the API user's profile time zone, not UTC: rendered
    # in UTC, a user west of Greenwich skips the pages changed in the last hours.
    seen: list[httpx.Request] = []
    inner = _confluence_handler(seen)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wiki/rest/api/user/current":
            seen.append(request)
            return httpx.Response(200, json={"displayName": "svc", "timeZone": "Europe/Istanbul"})
        return inner(request)

    base = {"base_url": "https://acme.atlassian.net/wiki", "auth_type": "bearer", "api_token": "p"}
    prior = SyncState(streams={"pages": {"cursor": "2026-01-02T00:00:00+00:00"}})

    cfg = ConfluenceSource.validate_config(base)
    src = ConfluenceSource(cfg, client=_client(handler, cfg.base_url))
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL, only=["pages"]
    )
    [i async for i in src.read(configured, prior)]
    assert 'lastmodified > "2026-01-02 03:00"' in seen[-1].url.params["cql"]
    assert sum(r.url.path.endswith("/user/current") for r in seen) == 1

    # A configured zone wins over the profile (service accounts without a profile zone).
    cfg = ConfluenceSource.validate_config({**base, "timezone": "America/New_York"})
    src = ConfluenceSource(cfg, client=_client(handler, cfg.base_url))
    [i async for i in src.read(configured, prior)]
    assert 'lastmodified > "2026-01-01 19:00"' in seen[-1].url.params["cql"]


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------

ADF = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": "Login "}, {"type": "text", "text": "fails"}],
        },
        {"type": "paragraph", "content": [{"type": "mention", "attrs": {"text": "@ann"}}]},
    ],
}

ISSUES = [
    {
        "id": "1",
        "key": "APP-1",
        "fields": {
            "summary": "Bug",
            "description": ADF,
            "status": {"name": "Open"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "project": {"key": "APP"},
            "assignee": {"displayName": "Ann"},
            "reporter": None,
            "labels": ["auth"],
            "created": "2026-01-01T09:00:00.000+0000",
            "updated": "2026-01-01T10:00:00.000+0000",
            "comment": {
                "comments": [
                    {
                        "id": "c1",
                        "author": {"displayName": "Bob"},
                        "body": ADF,
                        "created": "2026-01-01T09:30:00.000+0000",
                    }
                ]
            },
        },
    },
    {
        "id": "2",
        "key": "APP-2",
        "fields": {
            "summary": "Feature",
            "description": None,
            "status": {"name": "Done"},
            "project": {"key": "APP"},
            "created": "2026-01-02T09:00:00.000+0000",
            "updated": "2026-01-04T10:00:00.000+0000",
            "comment": {"comments": []},
        },
    },
]


def _jira_cloud_handler(seen: list[httpx.Request]):  # noqa: ANN202
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/rest/api/2/myself":
            return httpx.Response(200, json={"displayName": "svc"})
        if path == "/rest/api/3/project/search":
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": "10",
                            "key": "APP",
                            "name": "App",
                            "projectTypeKey": "software",
                            "lead": {"displayName": "Ann"},
                        }
                    ],
                    "isLast": True,
                    "startAt": 0,
                },
            )
        if path == "/rest/api/3/search/jql":
            jql = request.url.params["jql"]
            issues = ISSUES
            if "updated >" in jql:
                issues = [i for i in ISSUES if i["fields"]["updated"] > "2026-01-03"]
            token = request.url.params.get("nextPageToken")
            if token is None and len(issues) > 1:
                return httpx.Response(
                    200, json={"issues": issues[:1], "nextPageToken": "t2", "isLast": False}
                )
            if token == "t2":
                return httpx.Response(200, json={"issues": issues[1:], "isLast": True})
            return httpx.Response(200, json={"issues": issues, "isLast": True})
        return httpx.Response(404)

    return handler


async def test_jira_cloud_projects_issues_and_adf() -> None:
    seen: list[httpx.Request] = []
    cfg = JiraSource.validate_config(
        {
            "base_url": "https://acme.atlassian.net",
            "email": "me@acme.com",
            "api_token": "tok",
            "project_keys": ["APP"],
        }
    )
    src = JiraSource(cfg, client=_client(_jira_cloud_handler(seen), cfg.base_url))
    assert (await src.check()).ok
    catalog = await src.discover()
    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    records = [i for i in items if isinstance(i, Record)]
    assert [r.stream for r in records] == ["projects", "issues", "issues"]
    assert records[0].data == {
        "id": "10",
        "key": "APP",
        "name": "App",
        "project_type": "software",
        "lead": "Ann",
    }
    issue = records[1].data
    assert issue["key"] == "APP-1" and issue["url"] == "https://acme.atlassian.net/browse/APP-1"
    assert issue["description"] == "Login fails\n@ann"
    assert (
        issue["comments"][0]["author"] == "Bob"
        and issue["comments"][0]["body"] == "Login fails\n@ann"
    )
    assert issue["updated"] == "2026-01-01T10:00:00+00:00"
    assert "comment" not in issue["fields"] and issue["fields"]["summary"] == "Bug"
    jql = next(r for r in seen if r.url.path.endswith("/search/jql")).url.params["jql"]
    assert jql == 'project in ("APP") ORDER BY updated ASC'


async def test_jira_incremental_jql_and_state() -> None:
    seen: list[httpx.Request] = []
    cfg = JiraSource.validate_config({"base_url": "https://acme.atlassian.net", "api_token": "t"})
    src = JiraSource(cfg, client=_client(_jira_cloud_handler(seen), cfg.base_url))
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["issues"]
    )
    prior = SyncState(streams={"issues": {"cursor": "2026-01-03T00:00:00+00:00"}})
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["key"] for i in items if isinstance(i, Record)] == ["APP-2"]
    assert items[-1] == State(stream="issues", data={"cursor": "2026-01-04T10:00:00+00:00"})
    assert 'updated > "2026/01/03 00:00"' in seen[-1].url.params["jql"]  # no profile zone: UTC


async def test_jira_renders_jql_dates_in_the_api_users_time_zone() -> None:
    # JQL date literals are read in the API user's profile time zone (``/myself``).
    seen: list[httpx.Request] = []
    inner = _jira_cloud_handler(seen)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/api/3/myself":
            seen.append(request)
            return httpx.Response(200, json={"displayName": "svc", "timeZone": "America/New_York"})
        return inner(request)

    cfg = JiraSource.validate_config({"base_url": "https://acme.atlassian.net", "api_token": "t"})
    src = JiraSource(cfg, client=_client(handler, cfg.base_url))
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL, only=["issues"]
    )
    prior = SyncState(streams={"issues": {"cursor": "2026-01-03T00:00:00+00:00"}})
    [i async for i in src.read(configured, prior)]
    assert 'updated > "2026/01/02 19:00"' in seen[-1].url.params["jql"]
    assert sum(r.url.path.endswith("/myself") for r in seen) == 1

    cfg = JiraSource.validate_config(
        {"base_url": "https://acme.atlassian.net", "api_token": "t", "timezone": "Asia/Tokyo"}
    )
    src = JiraSource(cfg, client=_client(handler, cfg.base_url))
    [i async for i in src.read(configured, prior)]
    assert 'updated > "2026/01/03 09:00"' in seen[-1].url.params["jql"]


async def test_jira_server_uses_start_at_paging() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rest/api/2/project":
            return httpx.Response(
                200, json=[{"id": "10", "key": "APP", "name": "App"}, {"id": "11", "key": "OTHER"}]
            )
        if request.url.path == "/rest/api/2/search":
            start = int(request.url.params["startAt"])
            calls.append(dict(request.url.params))
            return httpx.Response(
                200, json={"issues": ISSUES[start : start + 1], "total": 2, "startAt": start}
            )
        return httpx.Response(404)

    cfg = JiraSource.validate_config(
        {
            "base_url": "https://jira.acme.com",
            "deployment": "server",
            "auth_type": "bearer",
            "api_token": "pat",
            "project_keys": ["APP"],
            "page_size": 1,
        }
    )
    src = JiraSource(cfg, client=_client(handler, cfg.base_url))
    catalog = await src.discover()
    records = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data.get("key") for r in records] == ["APP", "APP-1", "APP-2"]
    assert [c["startAt"] for c in calls] == ["0", "1"]
    assert json.dumps(JiraSource.spec().connection_specification)  # serialisable


async def test_jira_without_token_checks_the_project_list_not_myself() -> None:
    seen: list[httpx.Request] = []

    def server(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert "authorization" not in request.headers
        if request.url.path == "/rest/api/2/myself":
            return httpx.Response(401, json={"message": "anonymous"})
        if request.url.path == "/rest/api/2/project":
            return httpx.Response(200, json=[{"id": "10", "key": "APP", "name": "App"}])
        return httpx.Response(404)

    def cloud(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/rest/api/3/project/search":
            return httpx.Response(200, json={"values": [], "isLast": True})
        return httpx.Response(401)

    cfg = JiraSource.validate_config(
        {"base_url": "https://jira.acme.com", "deployment": "server", "project_keys": ["APP"]}
    )
    assert (await JiraSource(cfg, client=_client(server, cfg.base_url)).check()).ok
    assert [r.url.path for r in seen] == ["/rest/api/2/project"]

    seen.clear()
    cloud_cfg = JiraSource.validate_config({"base_url": "https://acme.atlassian.net"})
    assert (await JiraSource(cloud_cfg, client=_client(cloud, cloud_cfg.base_url)).check()).ok
    assert seen[0].url.path == "/rest/api/3/project/search"
    assert seen[0].url.params["maxResults"] == "1"
