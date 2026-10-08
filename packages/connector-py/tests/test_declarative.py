"""The declarative engine itself: paginators, parent/child streams, cursors, hooks."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from connector import ConnectorDefinition, ConnectorKind
from connector.common.declarative import (
    ContinueParamsPagination,
    CursorPagination,
    DeclarativeRestSource,
    LastRecordPagination,
    LinkHeaderPagination,
    NextUrlPagination,
    OffsetPagination,
    PageNumberPagination,
    StreamSpec,
    _parent_fields_used,
    as_epoch_millis,
    as_epoch_seconds,
    dig,
    is_newer,
    later,
)
from connector.common.rest_source import parse_iso
from tests.fake_api import FakeApi, read_all


class _Cfg(BaseModel):
    pass


def _source(specs: list[StreamSpec], api: FakeApi) -> DeclarativeRestSource:
    class _Src(DeclarativeRestSource[_Cfg]):
        definition = ConnectorDefinition(name="t", display_name="T", kind=ConnectorKind.SOURCE)
        Config = _Cfg

        def base_url(self) -> str:
            return "https://api.test"

        def streams(self) -> list[StreamSpec]:
            return specs

    return _Src(_Cfg(), client=api.client())


def _ids(records: dict[str, list[dict[str, Any]]], stream: str = "s") -> list[Any]:
    return [r["id"] for r in records.get(stream, [])]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def test_dig_and_cursor_ordering() -> None:
    assert dig({"a": {"b": [{"c": 1}, {"c": 2}]}}, "a.b.1.c") == 2
    assert dig({"a": 1}, "a.b") is None and dig([1, 2], "-1") == 2
    assert is_newer("2026-01-02T00:00:00Z", "2026-01-01T23:59:59+00:00")
    assert is_newer("1700000000.000300", "1700000000.000200")  # Slack ts
    assert is_newer("1700000000001", 1700000000000) and not is_newer(None, 1)
    assert later(None, "2026-01-01T00:00:00Z") == "2026-01-01T00:00:00+00:00"
    assert later("5", "12") == "12" and later("b", "a") == "b"


def test_numeric_strings_are_not_parsed_as_compact_iso_dates() -> None:
    assert parse_iso("20240101") is None and parse_iso("1700000000.5") is None
    assert as_epoch_seconds("2026-01-01T00:00:00Z") == 1767225600
    assert as_epoch_millis("1700000000000") == 1700000000000


# ---------------------------------------------------------------------------
# paginators
# ---------------------------------------------------------------------------


async def test_offset_pagination_stops_on_short_page_and_total() -> None:
    def handler(request: httpx.Request) -> dict[str, Any]:
        offset = int(request.url.params["offset"])
        return {"data": [{"id": i} for i in range(offset, min(offset + 2, 5))], "total": 5}

    api = FakeApi({"/items": handler})
    spec = StreamSpec(
        name="s", path="/items", records_path="data", paginator=OffsetPagination(page_size=2)
    )
    records, _ = await read_all(_source([spec], api))
    assert _ids(records) == [0, 1, 2, 3, 4]
    assert [r.url.params["offset"] for r in api.requests] == ["0", "2", "4"]


async def test_page_number_pagination_with_last_page_flag() -> None:
    def handler(request: httpx.Request) -> dict[str, Any]:
        page = int(request.url.params["page"])
        return {"tasks": [{"id": page}], "last_page": page == 2}

    api = FakeApi({"/t": handler})
    spec = StreamSpec(
        name="s",
        path="/t",
        records_path="tasks",
        paginator=PageNumberPagination(size_param=None, first_page=0, last_page_path="last_page"),
    )
    records, _ = await read_all(_source([spec], api))
    assert _ids(records) == [0, 1, 2]


async def test_cursor_pagination_in_body() -> None:
    def handler(request: httpx.Request) -> dict[str, Any]:
        import json

        body = json.loads(request.content)
        first = "start_cursor" not in body
        return {
            "results": [{"id": "a" if first else "b"}],
            "has_more": first,
            "next_cursor": "c2" if first else None,
        }

    api = FakeApi({"POST /search": handler})
    spec = StreamSpec(
        name="s",
        path="/search",
        method="POST",
        body={"q": 1},
        records_path="results",
        paginator=CursorPagination(
            cursor_path="next_cursor", cursor_param="start_cursor", in_body=True, size_param="n"
        ),
    )
    records, _ = await read_all(_source([spec], api))
    assert _ids(records) == ["a", "b"]


async def test_next_url_link_header_last_record_and_continue() -> None:
    api = FakeApi(
        {
            "/n": lambda r: (
                {"values": [{"id": 1}], "next": "https://api.test/n?page=2"}
                if "page" not in r.url.params
                else {"values": [{"id": 2}]}
            ),
            "/l": lambda r: (
                httpx.Response(
                    200, json=[{"id": 1}], headers={"Link": '<https://api.test/l?p=2>; rel="next"'}
                )
                if "p" not in r.url.params
                else httpx.Response(200, json=[{"id": 2}])
            ),
            "/b": lambda r: (
                [{"id": 9}, {"id": 8}]
                if "before" not in r.url.params
                else [{"id": 7}]
                if r.url.params["before"] == "8"
                else []
            ),
            "/c": lambda r: (
                {"query": {"pages": [{"id": 1}]}, "continue": {"gapcontinue": "B", "continue": "-"}}
                if "gapcontinue" not in r.url.params
                else {"query": {"pages": [{"id": 2}]}}
            ),
        }
    )
    specs = [
        StreamSpec(name="n", path="/n", records_path="values", paginator=NextUrlPagination()),
        StreamSpec(name="l", path="/l", paginator=LinkHeaderPagination(size_param=None)),
        StreamSpec(
            name="b", path="/b", paginator=LastRecordPagination(param="before", size_param=None)
        ),
        StreamSpec(
            name="c", path="/c", records_path="query.pages", paginator=ContinueParamsPagination()
        ),
    ]
    records, _ = await read_all(_source(specs, api))
    assert _ids(records, "n") == [1, 2] and _ids(records, "l") == [1, 2]
    assert _ids(records, "b") == [9, 8, 7] and _ids(records, "c") == [1, 2]


async def test_continue_pagination_drops_the_exhausted_sub_query_token() -> None:
    """MediaWiki: once ``rvcontinue`` finishes, the next generator page must not resend it."""

    def handler(request: httpx.Request) -> dict[str, Any]:
        p = request.url.params
        if "gapcontinue" in p:
            return {"query": {"pages": [{"id": 3}]}}
        if "rvcontinue" in p:
            return {
                "query": {"pages": [{"id": 2}]},
                "continue": {"gapcontinue": "B", "continue": "gapcontinue||"},
            }
        return {"query": {"pages": [{"id": 1}]}, "continue": {"rvcontinue": "X", "continue": "||"}}

    api = FakeApi({"/w": handler})
    spec = StreamSpec(
        name="s", path="/w", records_path="query.pages", paginator=ContinueParamsPagination()
    )
    records, _ = await read_all(_source([spec], api))
    assert _ids(records) == [1, 2, 3]
    last = api.requests[-1].url.params
    assert "rvcontinue" not in last and last["gapcontinue"] == "B"


# ---------------------------------------------------------------------------
# incremental, parents, hooks
# ---------------------------------------------------------------------------


async def test_server_side_incremental_and_client_side_filter() -> None:
    rows = [{"id": 1, "u": "2026-01-01T00:00:00Z"}, {"id": 2, "u": "2026-01-03T00:00:00Z"}]
    api = FakeApi({"/server": rows[1:], "/client": rows})
    specs = [
        StreamSpec(
            name="server",
            path="/server",
            cursor_field="u",
            incremental_param="since",
            cursor_format=as_epoch_seconds,
        ),
        StreamSpec(name="client", path="/client", cursor_field="u", client_side_filter=True),
    ]
    prior = {
        "server": {"cursor": "2026-01-02T00:00:00Z"},
        "client": {"cursor": "2026-01-02T00:00:00Z"},
    }
    records, states = await read_all(_source(specs, api), incremental=True, state=prior)
    assert _ids(records, "server") == [2] and _ids(records, "client") == [2]
    assert api.calls("/server")[0].url.params["since"] == "1767312000"
    assert "since" not in api.calls("/client")[0].url.params
    assert states["server"] == {"cursor": "2026-01-03T00:00:00+00:00"}


async def test_a_newest_first_list_stops_at_the_first_page_already_seen() -> None:
    # Ordered by the cursor descending, a page that is entirely older than the cursor means
    # every later page is too: walking the rest of the history each run buys nothing.
    pages = {
        1: [{"id": 5, "u": "2026-01-05T00:00:00Z"}, {"id": 4, "u": "2026-01-04T00:00:00Z"}],
        2: [{"id": 2, "u": "2026-01-02T00:00:00Z"}, {"id": 1, "u": "2026-01-01T00:00:00Z"}],
        3: [{"id": 0, "u": "2025-12-31T00:00:00Z"}],
    }
    api = FakeApi({"/desc": lambda r: pages[int(r.url.params["page"])]})
    spec = StreamSpec(
        name="s",
        path="/desc",
        paginator=PageNumberPagination(page_size=2),
        cursor_field="u",
        client_side_filter=True,
        stop_when_page_seen=True,
    )
    prior = {"s": {"cursor": "2026-01-03T00:00:00Z"}}
    records, states = await read_all(_source([spec], api), incremental=True, state=prior)
    assert _ids(records) == [5, 4]
    assert [c.url.params["page"] for c in api.calls("/desc")] == ["1", "2"]
    assert states["s"] == {"cursor": "2026-01-05T00:00:00+00:00"}

    # Without a cursor (first run) every page is read.
    full, _ = await read_all(_source([spec], api), incremental=True)
    assert _ids(full) == [5, 4, 2, 1, 0]


async def test_declarative_cursor_is_held_back_to_the_start_of_the_read() -> None:
    from datetime import UTC, datetime, timedelta

    from connector.common.cursor import CURSOR_SKEW_SECONDS

    now = datetime.now(UTC)
    rows = [{"id": 1, "u": (now + timedelta(minutes=2)).isoformat()}]
    api = FakeApi({"/s": rows})
    specs = [StreamSpec(name="s", path="/s", cursor_field="u", client_side_filter=True)]
    before = datetime.now(UTC)
    _, states = await read_all(_source(specs, api), incremental=True)
    cursor = parse_iso(states["s"]["cursor"])
    assert cursor is not None
    assert before - timedelta(seconds=CURSOR_SKEW_SECONDS) <= cursor <= datetime.now(UTC)


async def test_parent_child_with_per_parent_cursor_and_skipped_parent() -> None:
    api = FakeApi(
        {
            "/channels": [{"id": "A"}, {"id": "B"}, {"id": "X"}],
            "/channels/A/messages": lambda r: (
                [{"id": 2, "ts": "20"}]
                if r.url.params.get("oldest") == "10"
                else [{"id": 1, "ts": "10"}, {"id": 2, "ts": "20"}]
            ),
            "/channels/B/messages": [{"id": 3, "ts": "15"}],
            "/channels/X/messages": httpx.Response(403, json={}),
        }
    )
    specs = [
        StreamSpec(name="channels", path="/channels"),
        StreamSpec(
            name="messages",
            path="/channels/{parent[id]}/messages",
            parent="channels",
            parent_field="channel_id",
            per_parent_cursor=True,
            cursor_field="ts",
            incremental_param="oldest",
            cursor_format=str,
        ),
    ]
    prior = {"messages": {"cursor": "10", "by_parent": {"A": "10"}}}
    records, states = await read_all(
        _source(specs, api), only=["messages"], incremental=True, state=prior
    )
    assert [(m["channel_id"], m["id"]) for m in records["messages"]] == [("A", 2), ("B", 3)]
    # B had no cursor yet, so it was read from the start even though the global cursor is 10
    assert "oldest" not in api.calls("/channels/B/messages")[0].url.params
    assert states["messages"] == {"cursor": "20", "by_parent": {"A": "20", "B": "15"}}


def _parent_pages(request: httpx.Request) -> list[dict[str, Any]]:
    offset = int(request.url.params.get("offset", 0))
    return [{"id": offset + 1, "name": f"p{offset + 1}", "blob": "x" * 10}] if offset < 2 else []


async def test_single_child_streams_its_parent_page_by_page() -> None:
    # One child per parent stream: the parent is not materialised; its pages are read as
    # the child consumes them, so memory is one page of parents, not every parent record.
    api = FakeApi(
        {
            "/parents": _parent_pages,
            "/parents/1/items": [{"id": 11}],
            "/parents/2/items": [{"id": 22}],
        }
    )
    specs = [
        StreamSpec(name="parents", path="/parents", paginator=OffsetPagination(page_size=1)),
        StreamSpec(name="items", path="/parents/{parent[id]}/items", parent="parents"),
    ]
    records, _ = await read_all(_source(specs, api), only=["items"])
    assert _ids(records, "items") == [11, 22]
    assert api.paths() == [
        "/parents",
        "/parents/1/items",
        "/parents",
        "/parents/2/items",
        "/parents",
    ]


async def test_shared_parent_is_read_once_and_kept_projected() -> None:
    api = FakeApi(
        {
            "/parents": _parent_pages,
            "/parents/1/items": [{"id": 11}],
            "/parents/2/items": [{"id": 22}],
            "/parents/p1/notes": [{"id": 31}],
            "/parents/p2/notes": [{"id": 32}],
        }
    )
    parents = StreamSpec(name="parents", path="/parents", paginator=OffsetPagination(page_size=1))
    items = StreamSpec(name="items", path="/parents/{parent[id]}/items", parent="parents")
    notes = StreamSpec(
        name="notes",
        path="/parents/{parent[name]}/notes",
        parent="parents",
        parent_field="parent_name",
        parent_key="name",
    )
    records, _ = await read_all(_source([parents, items, notes], api), only=["items", "notes"])
    assert _ids(records, "items") == [11, 22]
    assert [(n["parent_name"], n["id"]) for n in records["notes"]] == [("p1", 31), ("p2", 32)]
    assert len(api.calls("/parents")) == 3  # two pages and the empty one: read once, not twice
    # What is kept for the siblings is the fields the children refer to (``id`` in the
    # path of ``items``, ``name`` for ``notes``), not the whole parent record.
    assert _parent_fields_used([items, notes]) == {"id", "name"}
    enriched = StreamSpec(name="x", path="/p/{parent[id]}", parent="parents", enrich="_hook")
    assert _parent_fields_used([items, enriched]) is None  # ``enrich`` sees the whole parent


async def test_parent_uses_cursor_reads_parents_changed_since_the_child_cursor() -> None:
    # Zendesk-style: tickets are exported from ``start_time``; a comment moves its ticket's
    # ``updated_at``, so the comments stream can ask for tickets changed since its cursor
    # instead of every ticket since the beginning of time.
    api = FakeApi(
        {
            "/tickets": lambda r: (
                [{"id": 2}]
                if r.url.params.get("start_time") == "1767312000"
                else [{"id": 1}, {"id": 2}]
            ),
            "/tickets/1/comments": [{"id": 10, "created_at": "2026-01-01T00:00:00Z"}],
            "/tickets/2/comments": [{"id": 20, "created_at": "2026-01-03T00:00:00Z"}],
        }
    )
    specs = [
        StreamSpec(
            name="tickets",
            path="/tickets",
            cursor_field="updated_at",
            incremental_param="start_time",
            cursor_format=as_epoch_seconds,
        ),
        StreamSpec(
            name="comments",
            path="/tickets/{parent[id]}/comments",
            parent="tickets",
            parent_uses_cursor=True,
            cursor_field="created_at",
            client_side_filter=True,
        ),
    ]
    prior = {"comments": {"cursor": "2026-01-02T00:00:00Z"}}
    records, states = await read_all(
        _source(specs, api), only=["comments"], incremental=True, state=prior
    )
    assert _ids(records, "comments") == [20]
    assert api.calls("/tickets")[0].url.params["start_time"] == "1767312000"
    assert states["comments"] == {"cursor": "2026-01-03T00:00:00+00:00"}


async def test_a_missing_detail_skips_that_record_only() -> None:
    # A listed item whose detail answers 404/403 (deleted meanwhile, no access) is one
    # record to skip - not the rest of the parent's records, not the whole stream.
    api = FakeApi(
        {
            "/items": [{"id": 1}, {"id": 2}, {"id": 3}],
            "/items/1": {"body": "one"},
            "/items/2": httpx.Response(404, json={}),
            "/items/3": {"body": "three"},
            "/parents": [{"id": "p"}],
            "/parents/p/kids": [{"id": 1}, {"id": 2}, {"id": 3}],
        }
    )
    top = StreamSpec(name="s", path="/items", detail_path="/items/{record[id]}")
    records, _ = await read_all(_source([top], api), only=["s"])
    assert [(r["id"], r["body"]) for r in records["s"]] == [(1, "one"), (3, "three")]

    parents = StreamSpec(name="parents", path="/parents")
    kids = StreamSpec(
        name="kids",
        path="/parents/{parent[id]}/kids",
        parent="parents",
        detail_path="/items/{record[id]}",
    )
    records, _ = await read_all(_source([parents, kids], api), only=["kids"])
    assert [r["id"] for r in records["kids"]] == [1, 3]

    # Other statuses are still failures of the stream.
    api.routes["/items/2"] = httpx.Response(500, json={})
    with pytest.raises(httpx.HTTPStatusError):
        await read_all(_source([top], api), only=["s"])


async def test_detail_expand_enrich_transform_and_error_check() -> None:
    api = FakeApi(
        {
            "/tree": {"pages": [{"id": 1, "kids": [{"id": 2}]}]},
            "/page/1": {"data": {"body": "one"}},
            "/page/2": {"data": {"body": "two"}},
            "/broken": {"ok": False, "error": "nope"},
        }
    )

    def expand(root: dict[str, Any]):  # noqa: ANN202
        for page in root["pages"]:
            yield {"id": page["id"]}
            yield from ({"id": k["id"]} for k in page["kids"])

    class _Src(DeclarativeRestSource[_Cfg]):
        definition = ConnectorDefinition(name="t2", display_name="T", kind=ConnectorKind.SOURCE)
        Config = _Cfg

        def base_url(self) -> str:
            return "https://api.test"

        async def _shout(self, rec: dict[str, Any], parent: Any) -> dict[str, Any]:
            rec["body"] = rec["body"].upper()
            return rec

        def streams(self) -> list[StreamSpec]:
            return [
                StreamSpec(
                    name="s",
                    path="/tree",
                    expand=expand,
                    detail_path="/page/{record[id]}",
                    detail_records_path="data",
                    enrich="_shout",
                    transform=lambda r: None if r["id"] == 2 else r,
                ),
                StreamSpec(
                    name="bad",
                    path="/broken",
                    error_check=lambda p: p.get("error") if p.get("ok") is False else None,
                ),
            ]

    src = _Src(_Cfg(), client=api.client())
    records, _ = await read_all(src, only=["s"])
    assert records["s"] == [{"id": 1, "body": "ONE"}]
    assert (await src.check()).ok
    broken = _source(
        [StreamSpec(name="bad", path="/broken", error_check=lambda p: p.get("error"))], api
    )
    result = await broken.check()
    assert not result.ok and "nope" in (result.message or "")


async def test_query_string_in_path_survives_params() -> None:
    api = FakeApi({"/tasks": [{"id": 1}]})
    spec = StreamSpec(name="s", path="/tasks?project=42", params={"fields": "a", "skip": None})
    await read_all(_source([spec], api))
    assert dict(api.requests[0].url.params) == {"project": "42", "fields": "a"}


async def test_repeated_page_stops_pagination_instead_of_looping() -> None:
    api = FakeApi({"/same": {"data": [{"id": 1}, {"id": 2}]}})  # ignores ?page=
    spec = StreamSpec(
        name="s",
        path="/same",
        records_path="data",
        paginator=PageNumberPagination(size_param=None),
    )
    records, _ = await read_all(_source([spec], api))
    assert _ids(records) == [1, 2] and len(api.requests) == 2
