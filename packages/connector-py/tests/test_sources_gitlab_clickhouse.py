"""GitLab and ClickHouse sources against fake HTTP endpoints (httpx MockTransport)."""

from __future__ import annotations

import json

import httpx
import pytest

from connector import ConfiguredCatalog, ConfigValidationError, Record, State, SyncMode, SyncState
from connector.sources.clickhouse import ClickHouseSource
from connector.sources.gitlab import GitLabSource

# ---------------------------------------------------------------------------
# GitLab
# ---------------------------------------------------------------------------

PROJECTS = [
    {
        "id": 1,
        "name": "api",
        "path_with_namespace": "acme/api",
        "web_url": "https://gl/acme/api",
        "default_branch": "main",
    },
    {
        "id": 2,
        "name": "web",
        "path_with_namespace": "acme/web",
        "web_url": "https://gl/acme/web",
        "wiki_enabled": False,
    },
]
ISSUES = {
    1: [
        {
            "id": 11,
            "iid": 1,
            "project_id": 1,
            "title": "Crash",
            "state": "opened",
            "labels": ["bug"],
            "author": {"username": "ann"},
            "web_url": "https://gl/acme/api/-/issues/1",
            "updated_at": "2026-01-01T10:00:00.000Z",
        },
        {
            "id": 12,
            "iid": 2,
            "project_id": 1,
            "title": "Slow",
            "state": "closed",
            "labels": [],
            "author": {"username": "bob"},
            "updated_at": "2026-01-03T10:00:00.000Z",
        },
    ],
    2: [],
}
MRS = {
    1: [
        {
            "id": 21,
            "iid": 5,
            "project_id": 1,
            "title": "Fix crash",
            "state": "merged",
            "source_branch": "fix",
            "target_branch": "main",
            "updated_at": "2026-01-02T10:00:00.000Z",
        }
    ],
    2: [],
}


def _gitlab_handler(seen: list[httpx.Request]):  # noqa: ANN202
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers.get("PRIVATE-TOKEN") == "glpat"
        path = request.url.path
        page = int(request.url.params.get("page", 1))
        if path == "/api/v4/user":
            return httpx.Response(200, json={"username": "svc"})
        if path == "/api/v4/groups/acme/projects":
            chunk = PROJECTS[page - 1 : page]
            headers = (
                {"x-next-page": str(page + 1)} if page < len(PROJECTS) else {"x-next-page": ""}
            )
            return httpx.Response(200, json=chunk, headers=headers)
        if path.startswith("/api/v4/projects/"):
            # httpx decodes %2F in .path; the raw path keeps the encoding the source sent.
            raw = request.url.raw_path.decode().split("?")[0]
            parts = raw.split("/")
            ident = parts[4]
            pid = int(ident) if ident.isdigit() else {"acme%2Fapi": 1, "acme%2Fweb": 2}[ident]
            kind = parts[5] if len(parts) > 5 else None
            if kind == "issues":
                items = ISSUES[pid]
                after = request.url.params.get("updated_after")
                if after:
                    items = [i for i in items if i["updated_at"] > after]
                return httpx.Response(200, json=items, headers={"x-next-page": ""})
            if kind == "merge_requests":
                return httpx.Response(200, json=MRS[pid], headers={"x-next-page": ""})
            if kind == "wikis":
                assert request.url.params["with_content"] == "1"
                return httpx.Response(
                    200,
                    json=[
                        {"slug": "home", "title": "Home", "format": "markdown", "content": "# Hi"}
                    ],
                )
            return httpx.Response(200, json=next(p for p in PROJECTS if p["id"] == pid))
        return httpx.Response(404)

    return handler


async def test_gitlab_group_projects_issues_mrs_wikis() -> None:
    seen: list[httpx.Request] = []
    cfg = GitLabSource.validate_config(
        {"base_url": "https://gl", "private_token": "glpat", "group_id": "acme", "page_size": 1}
    )
    src = GitLabSource(
        cfg,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(_gitlab_handler(seen)), base_url="https://gl"
        ),
    )
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["projects", "issues", "merge_requests", "wiki_pages"]
    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    records = [i for i in items if isinstance(i, Record)]
    by_stream = {}
    for r in records:
        by_stream.setdefault(r.stream, []).append(r.data)
    assert [p["id"] for p in by_stream["projects"]] == [1, 2]  # paged via x-next-page
    assert [i["title"] for i in by_stream["issues"]] == ["Crash", "Slow"]
    assert by_stream["issues"][0]["author"] == "ann" and by_stream["issues"][0]["labels"] == ["bug"]
    assert by_stream["merge_requests"][0]["source_branch"] == "fix"
    assert by_stream["wiki_pages"] == [
        {
            "project_id": 1,
            "slug": "home",
            "title": "Home",
            "format": "markdown",
            "content": "# Hi",
            "web_url": "https://gl/acme/api/-/wikis/home",
        }
    ]  # project 2 has wiki disabled
    assert not any(isinstance(i, State) for i in items)


async def test_gitlab_incremental_updated_after_and_explicit_projects() -> None:
    seen: list[httpx.Request] = []
    cfg = GitLabSource.validate_config(
        {"base_url": "https://gl", "private_token": "glpat", "project_ids": ["acme/api"]}
    )
    src = GitLabSource(
        cfg,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(_gitlab_handler(seen)), base_url="https://gl"
        ),
    )
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["issues"]
    )
    prior = SyncState(streams={"issues": {"cursor": "2026-01-02T00:00:00+00:00"}})
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["title"] for i in items if isinstance(i, Record)] == ["Slow"]
    assert items[-1] == State(stream="issues", data={"cursor": "2026-01-03T10:00:00+00:00"})
    assert seen[0].url.raw_path.startswith(b"/api/v4/projects/acme%2Fapi")  # path encoded
    assert seen[1].url.params["updated_after"] == "2026-01-02T00:00:00+00:00"


def test_gitlab_requires_group_or_projects() -> None:
    with pytest.raises(ConfigValidationError):
        GitLabSource.validate_config({"base_url": "https://gl", "private_token": "x"})


async def test_gitlab_without_token_is_anonymous_and_skips_forbidden_wikis() -> None:
    # Anonymous project payloads carry no ``wiki_enabled``; a disabled wiki answers 403.
    docs = {"id": 3, "name": "docs", "path_with_namespace": "acme/docs", "web_url": "https://gl/d"}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert "PRIVATE-TOKEN" not in request.headers
        raw = request.url.raw_path.decode().split("?")[0]
        if raw == "/api/v4/user":
            return httpx.Response(401, json={"message": "401 Unauthorized"})
        if raw == "/api/v4/projects/acme%2Fapi":
            return httpx.Response(200, json=PROJECTS[0])
        if raw == "/api/v4/projects/acme%2Fdocs":
            return httpx.Response(200, json=docs)
        if raw == "/api/v4/projects/1/wikis":
            return httpx.Response(403, json={"message": "403 Forbidden"})
        if raw == "/api/v4/projects/3/wikis":
            page = {"slug": "home", "title": "Home", "format": "markdown", "content": "# Hi"}
            return httpx.Response(200, json=[page])
        return httpx.Response(404)

    cfg = GitLabSource.validate_config(
        {"base_url": "https://gl", "project_ids": ["acme/api", "acme/docs"]}
    )
    src = GitLabSource(
        cfg,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://gl"),
    )
    assert (await src.check()).ok  # the first configured project, not /user
    assert seen[0].url.raw_path.startswith(b"/api/v4/projects/acme%2Fapi")
    catalog = await src.discover()
    items = [
        i async for i in src.read(ConfiguredCatalog.from_catalog(catalog, only=["wiki_pages"]))
    ]
    pages = [i.data for i in items if isinstance(i, Record)]
    assert [(p["project_id"], p["slug"]) for p in pages] == [(3, "home")]


# ---------------------------------------------------------------------------
# ClickHouse
# ---------------------------------------------------------------------------

COLUMNS = [
    {"table": "events", "name": "id", "type": "UInt64", "is_in_primary_key": 1},
    {"table": "events", "name": "ts", "type": "DateTime", "is_in_primary_key": 0},
    {"table": "events", "name": "payload", "type": "Nullable(String)", "is_in_primary_key": 0},
    {"table": "events", "name": "score", "type": "Float32", "is_in_primary_key": 0},
    {"table": "tags", "name": "name", "type": "LowCardinality(String)", "is_in_primary_key": 1},
]
EVENTS = [
    {"id": 1, "ts": "2026-01-01 10:00:00", "payload": "a", "score": 0.5},
    {"id": 2, "ts": "2026-01-02 10:00:00", "payload": None, "score": 1.5},
    {"id": 3, "ts": "2026-01-03 10:00:00", "payload": "c", "score": 2.5},
]


def _jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


def _clickhouse_handler(seen: list[tuple[str, dict]]):  # noqa: ANN202
    def handler(request: httpx.Request) -> httpx.Response:
        sql = request.content.decode()
        seen.append((sql, dict(request.url.params)))
        assert request.headers["Authorization"].startswith("Basic ")
        assert request.url.params["default_format"] == "JSONEachRow"
        if sql.startswith("SELECT 1"):
            return httpx.Response(200, text='{"1":1}\n')
        if "system.columns" in sql:
            assert request.url.params["param_db"] == "analytics"
            return httpx.Response(200, text=_jsonl(COLUMNS))
        if "`analytics`.`events`" in sql:
            rows = EVENTS
            if "WHERE" in sql:
                rows = [r for r in rows if r["ts"] > request.url.params["param_last"]]
            return httpx.Response(200, text=_jsonl(rows))
        if "`analytics`.`tags`" in sql:
            return httpx.Response(200, text=_jsonl([{"name": "x"}]))
        return httpx.Response(400, text="unknown query")

    return handler


def _ch(seen, **cfg) -> ClickHouseSource:  # noqa: ANN001, ANN003
    config = ClickHouseSource.validate_config(
        {"url": "http://ch:8123", "database": "analytics", "password": "p", **cfg}
    )
    return ClickHouseSource(
        config,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(_clickhouse_handler(seen)), base_url="http://ch:8123"
        ),
    )


async def test_clickhouse_check_discover_and_stream() -> None:
    seen: list[tuple[str, dict]] = []
    src = _ch(seen)
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["events", "tags"]
    events = catalog.get("events")
    assert events.json_schema["properties"] == {
        "id": {"type": "integer"},
        "ts": {"type": "string"},
        "payload": {"type": "string"},
        "score": {"type": "number"},
    }
    assert events.source_defined_primary_key == [["id"]]
    assert events.supported_sync_modes == [SyncMode.FULL_REFRESH]
    records = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [(r.stream, r.data.get("id", r.data.get("name"))) for r in records] == [
        ("events", 1),
        ("events", 2),
        ("events", 3),
        ("tags", "x"),
    ]
    assert records[1].data["payload"] is None


async def test_clickhouse_incremental_with_bound_parameter() -> None:
    seen: list[tuple[str, dict]] = []
    src = _ch(seen, cursor_columns={"events": "ts"}, tables=["events"])
    catalog = await src.discover()
    assert SyncMode.INCREMENTAL in catalog.get("events").supported_sync_modes
    configured = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL)
    prior = SyncState(streams={"events": {"cursor": "2026-01-01 10:00:00"}})
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["id"] for i in items if isinstance(i, Record)] == [2, 3]
    assert items[-1] == State(stream="events", data={"cursor": "2026-01-03 10:00:00"})
    sql, params = seen[-1]
    assert sql == "SELECT * FROM `analytics`.`events` WHERE `ts` > {last:String} ORDER BY `ts` ASC"
    assert params["param_last"] == "2026-01-01 10:00:00"  # value is bound, never interpolated


async def test_clickhouse_http_error_surfaces() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Code: 60. DB::Exception: Table missing")

    cfg = ClickHouseSource.validate_config({"url": "http://ch:8123"})
    src = ClickHouseSource(
        cfg,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ch:8123"),
    )
    result = await src.check()
    assert not result.ok and "500" in (result.message or "")


async def test_clickhouse_asks_for_unquoted_64bit_integers_unless_told_otherwise() -> None:
    # Live 26.9 defaults the setting to 0; older servers default to 1 and would hand UInt64
    # columns over as quoted strings against the declared "integer".
    seen: list[tuple[str, dict]] = []
    assert (await _ch(seen).check()).ok
    assert seen[0][1]["output_format_json_quote_64bit_integers"] == "0"

    seen.clear()
    overridden = _ch(seen, settings={"output_format_json_quote_64bit_integers": "1"})
    assert (await overridden.check()).ok
    assert seen[0][1]["output_format_json_quote_64bit_integers"] == "1"
