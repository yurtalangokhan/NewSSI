from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from connector import CheckFailedError, ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.sources.http_json import HttpJsonSource
from connector.sources.jsonl_file import JsonlFileSource

# ---------------------------------------------------------------------------
# jsonl_file
# ---------------------------------------------------------------------------


async def test_jsonl_discover_and_full_refresh(jsonl_dir: Path) -> None:
    src = JsonlFileSource.from_config({"directory": str(jsonl_dir)})
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["orders", "users"]
    assert catalog.get("users").json_schema["properties"]["name"] == {"type": "string"}
    assert catalog.get("users").supported_sync_modes == [SyncMode.FULL_REFRESH]

    rows = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog, only=["users"]))]
    assert all(isinstance(r, Record) for r in rows)
    assert len(rows) == 5


async def test_jsonl_incremental_cursor(jsonl_dir: Path) -> None:
    src = JsonlFileSource.from_config({"directory": str(jsonl_dir), "cursor_field": "updated_at"})
    catalog = await src.discover()
    assert SyncMode.INCREMENTAL in catalog.get("users").supported_sync_modes
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["users"]
    )

    items = [i async for i in src.read(configured, SyncState(streams={"users": {"cursor": 30}}))]
    records = [i for i in items if isinstance(i, Record)]
    states = [i for i in items if isinstance(i, State)]
    assert [r.data["id"] for r in records] == [4, 5]
    assert states == [State(stream="users", data={"cursor": 50})]


async def test_jsonl_reads_files_off_the_event_loop(
    jsonl_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Files are parsed in a worker thread: a large file must not stall the host process.
    import threading

    from connector.sources import jsonl_file as module

    loop_thread = threading.get_ident()
    seen: list[int] = []
    real_open = Path.open

    def spying_open(self: Path, *args: object, **kwargs: object) -> object:
        seen.append(threading.get_ident())
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spying_open)
    src = JsonlFileSource.from_config({"directory": str(jsonl_dir)})
    catalog = await src.discover()
    rows = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog, only=["users"]))]
    assert len(rows) == 5
    assert seen and all(ident != loop_thread for ident in seen)
    assert module.iterate_in_thread  # the reader streams rows through the shared helper


async def test_jsonl_check_failures(tmp_path: Path) -> None:
    src = JsonlFileSource.from_config({"directory": str(tmp_path / "missing")})
    assert not (await src.check()).ok
    with pytest.raises(CheckFailedError):
        await src.discover()


# ---------------------------------------------------------------------------
# http_json
# ---------------------------------------------------------------------------


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://api.test")


async def test_http_json_records_path_and_bearer() -> None:
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"data": {"items": [{"id": 1}, {"id": 2}]}})

    cfg = HttpJsonSource.validate_config(
        {
            "url": "http://api.test/items",
            "records_path": "data.items",
            "stream_name": "items",
            "bearer_token": "t",
        }
    )
    # The injected client knows nothing about the token: the source sends it.
    src = HttpJsonSource(cfg, client=_client(handler))
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["items"] and "id" in catalog.get("items").json_schema["properties"]
    rows = [r async for r in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["id"] for r in rows] == [1, 2]
    assert seen_auth and all(a == "Bearer t" for a in seen_auth)


async def test_http_json_page_pagination_stops_on_empty() -> None:
    pages = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 3}], 3: []}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages.get(page, []))

    cfg = HttpJsonSource.validate_config(
        {
            "url": "http://api.test/list",
            "pagination": "page",
            "page_size_param": "limit",
            "page_size": 2,
        }
    )
    src = HttpJsonSource(cfg, client=_client(handler))
    catalog = await src.discover()
    rows = [r async for r in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["id"] for r in rows] == [1, 2, 3]


async def test_http_json_stops_when_the_api_serves_the_same_page_again() -> None:
    # An API that ignores ``page`` (or clamps it to its last page) must not be read
    # ``max_pages`` times with every record duplicated.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}])

    cfg = HttpJsonSource.validate_config(
        {"url": "http://api.test/list", "pagination": "page", "max_pages": 50}
    )
    src = HttpJsonSource(cfg, client=_client(handler))
    catalog = await src.discover()
    rows = [r async for r in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["id"] for r in rows] == [1, 2]
    assert calls == 3  # discover + first page + the repeated page that stops the read


async def test_http_json_cursor_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(200, json={"items": [{"id": "a"}], "meta": {"next": "c2"}})
        if cursor == "c2":
            return httpx.Response(200, json={"items": [{"id": "b"}], "meta": {"next": None}})
        raise AssertionError(f"unexpected cursor {cursor}")

    cfg = HttpJsonSource.validate_config(
        {
            "url": "http://api.test/x",
            "records_path": "items",
            "pagination": "cursor",
            "next_cursor_path": "meta.next",
        }
    )
    src = HttpJsonSource(cfg, client=_client(handler))
    catalog = await src.discover()
    rows = [r async for r in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert [r.data["id"] for r in rows] == ["a", "b"]


async def test_http_json_check_reports_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return handler(request) if len(calls) < 3 else httpx.Response(200, json=[{"id": 1}])

    cfg = HttpJsonSource.validate_config({"url": "http://api.test/x"})
    src = HttpJsonSource(cfg, client=_client(handler))
    src.retry_delay = 0
    result = await src.check()
    assert not result.ok and "503" in (result.message or "")

    # A transient failure is retried like for every other API source.
    recovering = HttpJsonSource(cfg, client=_client(flaky))
    recovering.retry_delay = 0
    assert (await recovering.check()).ok and len(calls) == 3


async def test_http_json_keeps_the_query_string_of_its_url() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json=[])

    cfg = HttpJsonSource.validate_config(
        {"url": "http://api.test/items?type=a", "pagination": "page", "params": {"lang": "tr"}}
    )
    src = HttpJsonSource(cfg, client=_client(handler))

    assert (await src.check()).ok
    # httpx replaces a URL's own query once ``params`` are passed; ``type=a`` must survive.
    assert requested == ["http://api.test/items?type=a&lang=tr&page=1"]


async def test_http_json_does_not_follow_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    hops: list[tuple[str, str | None]] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        hops.append((request.url.host, request.headers.get("x-api-key")))
        if request.url.host == "api.test":
            return httpx.Response(302, headers={"Location": "https://elsewhere.test/collect"})
        return httpx.Response(200, json=[{"id": 1}])

    real_client = httpx.AsyncClient

    def client_with_fake_network(**kwargs):  # noqa: ANN003, ANN202
        return real_client(transport=httpx.MockTransport(redirecting), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_with_fake_network)
    cfg = HttpJsonSource.validate_config(
        {"url": "https://api.test/items", "headers": {"X-Api-Key": "K-SECRET"}}
    )
    src = HttpJsonSource(cfg)  # builds its own client, as it does in a sync
    try:
        result = await src.check()
    finally:
        await src.close()

    # A configured header (an API key, say) must not travel to wherever a 3xx points.
    assert hops == [("api.test", "K-SECRET")]
    assert not result.ok and "302" in (result.message or "")


async def test_a_retried_request_is_logged_without_the_query_of_its_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = HttpJsonSource.validate_config({"url": "http://api.test/items?api_key=K-SECRET"})
    src = HttpJsonSource(cfg, client=_client(lambda request: httpx.Response(503, text="down")))
    src.retry_delay = 0

    with caplog.at_level("WARNING", logger="connector.rest"):
        assert not (await src.check()).ok

    assert "failed (attempt 1)" in caplog.text and "http://api.test/items" in caplog.text
    assert "K-SECRET" not in caplog.text


async def test_rate_limits_wait_longer_and_honour_http_date_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Many APIs answer 429 without Retry-After and keep refusing for tens of seconds:
    # a half-second wait and three attempts give up inside the penalty. Rate limits get
    # a longer, growing wait and more attempts; an HTTP-date Retry-After is read too.
    from email.utils import format_datetime

    from connector.common import rest_source

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(rest_source.asyncio, "sleep", fake_sleep)
    answers: list[httpx.Response] = [
        httpx.Response(429, text="slow down"),
        httpx.Response(429, text="slow down"),
        httpx.Response(429, text="slow down"),
        httpx.Response(200, json=[{"id": 1}]),
    ]
    cfg = HttpJsonSource.validate_config({"url": "http://api.test/x"})
    src = HttpJsonSource(cfg, client=_client(lambda request: answers.pop(0)))
    assert (await src.check()).ok
    # 2 s, 4 s, 8 s with ±20 % jitter
    assert len(slept) == 3 and slept[0] >= 1.6 and slept[1] >= 3.2 and slept[2] >= 6.4

    slept.clear()
    retry_at = format_datetime(datetime.now(UTC) + timedelta(seconds=7), usegmt=True)
    answers[:] = [
        httpx.Response(429, headers={"Retry-After": retry_at}),
        httpx.Response(200, json=[{"id": 1}]),
    ]
    assert (await src.check()).ok
    assert len(slept) == 1 and 5.0 <= slept[0] <= 7.5


async def test_a_403_that_is_a_rate_limit_waits_for_the_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GitHub's primary rate limit answers 403 (not 429) with x-ratelimit-remaining: 0 and the
    # reset time; treated as "forbidden" it would skip the rest of the repositories silently.
    from connector.common import rest_source

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(rest_source.asyncio, "sleep", fake_sleep)
    reset = str(int((datetime.now(UTC) + timedelta(seconds=90)).timestamp()))
    answers: list[httpx.Response] = [
        httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": reset},
        ),
        httpx.Response(200, json=[{"id": 1}]),
    ]
    cfg = HttpJsonSource.validate_config({"url": "http://api.test/x"})
    src = HttpJsonSource(cfg, client=_client(lambda request: answers.pop(0)))
    assert (await src.check()).ok
    assert len(slept) == 1 and 85.0 <= slept[0] <= 91.0

    # A plain 403 is still final: no retry, no wait.
    slept.clear()
    answers[:] = [httpx.Response(403, json={"message": "Forbidden"})]
    assert not (await src.check()).ok and slept == [] and answers == []


async def test_jsonl_integer_cursor_beyond_what_a_float_can_hold(tmp_path: Path) -> None:
    big = 2**53
    (tmp_path / "events.jsonl").write_text(
        "\n".join(json.dumps({"id": big + i}) for i in range(3)), encoding="utf-8"
    )
    src = JsonlFileSource.from_config({"directory": str(tmp_path), "cursor_field": "id"})
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )

    items = [i async for i in src.read(configured, SyncState(streams={"events": {"cursor": big}}))]

    assert [i.data["id"] for i in items if isinstance(i, Record)] == [big + 1, big + 2]
    assert items[-1] == State(stream="events", data={"cursor": big + 2})


def test_http_json_config_round_trip_is_json_schema() -> None:
    schema = HttpJsonSource.spec().connection_specification
    json.dumps(schema)  # must be serialisable for the frontend SchemaForm
    assert schema["required"] == ["url"]
