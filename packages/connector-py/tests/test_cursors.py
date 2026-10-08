"""Incremental cursors and the helpers the table-shaped sources share."""

from __future__ import annotations

import datetime as dt
import decimal
import threading
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from connector import (
    ConfiguredCatalog,
    Connection,
    ConnectorRegistry,
    DestinationSyncMode,
    JobStatus,
    Record,
    State,
    SyncMode,
    SyncOptions,
    SyncRunner,
    SyncState,
)
from connector.common.blocking import iterate_in_thread
from connector.common.cursor import (
    CURSOR_SKEW_SECONDS,
    CursorTracker,
    incremental_cursor,
    is_newer,
)
from connector.common.tabular import (
    ansi_ident,
    backtick_ident,
    bracket_ident,
    from_json_scalar,
    is_exact_cursor,
    table_stream,
    to_json_value,
)
from connector.destinations.memory import InMemoryDestination
from connector.sources.clickhouse import ClickHouseSource
from tests.conftest import FakeSource
from tests.test_sources_db import _MYSQL_ROWS, _mysql_source

# ---- tracker ---------------------------------------------------------------------------


def _states(tracker: CursorTracker, values: list[Any], **kw: Any) -> list[Any]:
    """The cursor of every checkpoint emitted while ``values`` are observed in order."""
    return [s.data["cursor"] for v in values if (s := tracker.observe(v, **kw)) is not None]


def test_a_disabled_tracker_remembers_nothing() -> None:
    state = SyncState(streams={"t": {"cursor": 5}})
    tracker = CursorTracker("t", state, enabled=False, ordered=True, checkpoint_every=1)
    assert tracker.start is None
    assert _states(tracker, [1, 2, 3]) == []
    assert tracker.final_state() is None


def test_unordered_keeps_the_latest_value_whatever_the_arrival_order() -> None:
    tracker = CursorTracker("t", SyncState(streams={"t": {"cursor": "2026-01-02T00:00:00Z"}}))
    assert tracker.start == "2026-01-02T00:00:00Z"
    for value in ("2026-01-05T00:00:00Z", None, "2026-01-03T00:00:00+00:00"):
        assert tracker.observe(value) is None  # never mid-stream
    assert tracker.final_state() == State(stream="t", data={"cursor": "2026-01-05T00:00:00+00:00"})


def test_unordered_cursor_is_held_back_to_the_start_of_the_read() -> None:
    # Records written to one partition (mailbox, project) while another is read carry
    # stamps below the final cursor, and a source clock ahead of ours lets stamps run past
    # "now". An unordered cursor is therefore capped at the start of the read minus a
    # margin: the next run reads those records again (record keys absorb duplicates)
    # instead of never.
    tracker = CursorTracker("t")
    cap = (tracker.started - dt.timedelta(seconds=CURSOR_SKEW_SECONDS)).isoformat()
    future = (tracker.started + dt.timedelta(minutes=2)).isoformat()
    tracker.observe(future)
    assert tracker.final_state() == State(stream="t", data={"cursor": cap})

    # A saved cursor past the cap is never moved back.
    saved = (tracker.started + dt.timedelta(minutes=1)).isoformat()
    tracker = CursorTracker("t", SyncState(streams={"t": {"cursor": saved}}))
    tracker.observe(future)
    assert tracker.final_state() == State(stream="t", data={"cursor": saved})

    # Ordered streams (one sorted query) and non-timestamp cursors are what they are.
    ordered = CursorTracker("t", ordered=True)
    ordered.observe(future)
    assert ordered.final_state() == State(stream="t", data={"cursor": future})
    numbers = CursorTracker("t")
    numbers.observe(10**12)
    assert numbers.final_state() == State(stream="t", data={"cursor": 10**12})


def test_ordered_takes_the_last_value_without_comparing() -> None:
    # 64-bit integers arrive as text from some servers: "10" sorts before "9" as a string.
    tracker = CursorTracker("t", ordered=True)
    _states(tracker, ["8", "9", "10"])
    assert tracker.final_state() == State(stream="t", data={"cursor": "10"})


def test_ordered_checkpoints_only_between_values() -> None:
    tracker = CursorTracker("t", ordered=True, checkpoint_every=2)
    # Rows 1,1,1 share a value: no checkpoint may fall among them, or a resumed run
    # (WHERE cursor > 1) would lose the ones not yet read.
    assert _states(tracker, [1, 1, 1]) == []
    # The first 2 proves every 1 has been delivered.
    assert _states(tracker, [2]) == [1]
    assert _states(tracker, [2, 3]) == [2]
    assert _states(tracker, [3]) == []
    assert tracker.final_state() == State(stream="t", data={"cursor": 3})


def test_ordered_does_not_repeat_a_checkpoint() -> None:
    tracker = CursorTracker("t", ordered=True, checkpoint_every=1)
    assert _states(tracker, [1, 2, 2, 2, 2]) == [1]


def test_inexact_values_are_never_a_checkpoint_boundary() -> None:
    # Text under a case-insensitive collation: the database may call "a" and "A" equal.
    tracker = CursorTracker("t", ordered=True, checkpoint_every=1)
    assert _states(tracker, ["a", "A", "b", "c"], exact=False) == []
    assert tracker.final_state() == State(stream="t", data={"cursor": "c"})


def test_resumes_from_the_saved_cursor() -> None:
    tracker = CursorTracker("t", SyncState(streams={"t": {"cursor": 7}}), ordered=True)
    assert tracker.start == 7
    # Nothing new: the cursor stays where it was.
    assert tracker.final_state() == State(stream="t", data={"cursor": 7})


async def test_incremental_cursor_of_a_configured_stream() -> None:
    catalog = await FakeSource.from_config({}).discover()
    full = ConfiguredCatalog.from_catalog(catalog).streams[0]
    incremental = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL).streams[0]
    assert incremental_cursor(full) is None
    assert incremental_cursor(incremental) == "id"
    incremental.cursor_field = []
    assert incremental_cursor(incremental) is None


def test_is_newer_compares_by_kind() -> None:
    assert is_newer(10, 9) and is_newer("10", "9") and not is_newer("9", "10")
    assert is_newer("2026-01-02T00:00:00Z", "2026-01-01T23:59:59+00:00")
    assert is_newer(1.5, 1) and is_newer("1.5", "1") and not is_newer(1, 1.5)


def test_integer_cursors_are_compared_exactly() -> None:
    # 64-bit ids. As floats, 2**53 and 2**53 + 1 are the same number.
    big = 2**53
    assert is_newer(big + 1, big) and not is_newer(big, big + 1) and not is_newer(big, big)
    assert is_newer(str(big + 1), str(big)) and is_newer(big + 1, str(big))
    assert is_newer(-big, -big - 1)

    tracker = CursorTracker("t", SyncState(streams={"t": {"cursor": big}}))
    for value in (big + 2, big + 1):
        tracker.observe(value)
    assert tracker.final_state() == State(stream="t", data={"cursor": big + 2})


# ---- tabular helpers ----------------------------------------------------------------------


def test_identifiers_are_quoted_and_escaped() -> None:
    assert ansi_ident('or"ders') == '"or""ders"'
    assert backtick_ident("or`ders") == "`or``ders`"
    assert bracket_ident("or]ders") == "[or]]ders]"


def test_driver_values_become_json() -> None:
    row = {
        "at": dt.datetime(2026, 1, 2, 3, 4, 5),
        "day": dt.date(2026, 1, 2),
        "took": dt.timedelta(seconds=90),
        "total": decimal.Decimal("9.50"),
        "id": uuid.UUID(int=1),
        "blob": memoryview(b"\x01\xff"),
        "tags": [dt.date(2026, 1, 1), ("a", 1)],
        "nested": {1: decimal.Decimal("1")},
        "plain": None,
    }
    assert to_json_value(row) == {
        "at": "2026-01-02T03:04:05",
        "day": "2026-01-02",
        "took": 90.0,
        "total": 9.5,
        "id": "00000000-0000-0000-0000-000000000001",
        "blob": "01ff",
        "tags": ["2026-01-01", ["a", 1]],
        "nested": {"1": 1.0},
        "plain": None,
    }
    assert to_json_value(object, default=lambda v: "custom") == "custom"
    assert from_json_scalar("2026-01-02T03:04:05") == dt.datetime(2026, 1, 2, 3, 4, 5)
    assert from_json_scalar("not a date") == "not a date" and from_json_scalar(5) == 5


def test_only_numbers_and_dates_are_exact_cursors() -> None:
    assert is_exact_cursor(5) and is_exact_cursor(dt.datetime(2026, 1, 1))
    assert not is_exact_cursor("abc") and not is_exact_cursor(b"abc")


def test_table_stream_is_incremental_only_with_a_cursor() -> None:
    plain = table_stream("t", {"id": {"type": "integer"}}, namespace="db")
    assert plain.supported_sync_modes == [SyncMode.FULL_REFRESH]
    assert plain.default_cursor_field == [] and plain.source_defined_primary_key == []
    tracked = table_stream("t", {}, cursor="updated_at", primary_key=[["id"]])
    assert tracked.supported_sync_modes == [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]
    assert tracked.default_cursor_field == ["updated_at"] and tracked.source_defined_cursor


async def test_blocking_iterators_are_drained_off_the_event_loop() -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def rows():  # noqa: ANN202
        for i in range(5):
            seen.append(threading.get_ident())
            yield i

    assert [i async for i in iterate_in_thread(rows(), chunk_size=2)] == [0, 1, 2, 3, 4]
    assert seen and loop_thread not in seen


# ---- sources -------------------------------------------------------------------------------


async def test_mysql_checkpoints_inside_a_large_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("connector.sources.mysql.CHECKPOINT_ROWS", 2)
    rows = [
        {"id": i, "total": decimal.Decimal(1), "updated_at": dt.datetime(2026, 1, day, 10)}
        for i, day in enumerate([1, 1, 1, 2, 3, 3, 4], start=1)
    ]
    src = _mysql_source(rows, cursor_col="updated_at")
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )
    items = [i async for i in src.read(configured)]

    order = [
        ("S", i.data["cursor"]) if isinstance(i, State) else ("R", i.data["id"]) for i in items
    ]
    assert order == [
        ("R", 1),
        ("R", 2),
        ("R", 3),
        # after three rows of day 1, the first row of day 2 closes day 1
        ("S", "2026-01-01T10:00:00"),
        ("R", 4),
        ("R", 5),
        # day 3 is not closed yet when the interval comes round again: day 2 is
        ("S", "2026-01-02T10:00:00"),
        ("R", 6),
        ("R", 7),
        ("S", "2026-01-04T10:00:00"),
    ]


async def test_mysql_identifiers_cannot_break_out_of_their_quotes() -> None:
    src = _mysql_source(_MYSQL_ROWS, cursor_col="id")
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL)
    configured.streams[0].cursor_field = ["id` DESC; DROP TABLE x; -- "]
    [i async for i in src.read(configured, SyncState(streams={"orders": {"cursor": 1}}))]
    sql, args = src._pool._conn._cursor.executed[-1]
    quoted = "`id`` DESC; DROP TABLE x; -- `"
    assert sql == f"SELECT * FROM `orders` WHERE {quoted} > %s ORDER BY {quoted} ASC"
    assert args == (1,)


async def test_mysql_a_percent_sign_in_a_name_survives_the_drivers_formatting() -> None:
    src = _mysql_source(_MYSQL_ROWS, cursor_col="id")
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )
    configured.streams[0].stream.name = "orders_100%"
    src._pool._conn._cursor._tables["orders_100%%"] = _MYSQL_ROWS

    [i async for i in src.read(configured, SyncState(streams={"orders_100%": {"cursor": 1}}))]

    sql, args = src._pool._conn._cursor.executed[-1]
    # aiomysql builds the statement with ``sql % escaped_args``: a bare "%" in a name
    # is a formatting error there, a doubled one is the name.
    assert sql % ("1",) == "SELECT * FROM `orders_100%` WHERE `id` > 1 ORDER BY `id` ASC"


async def test_clickhouse_numeric_cursor_follows_the_server_order() -> None:
    # 64-bit integers are quoted in ClickHouse's JSON output.
    rows = [{"n": "8"}, {"n": "9"}, {"n": "10"}, {"n": "11"}]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sql = request.content.decode()
        seen.append(sql)
        if "system.columns" in sql:
            line = '{"table":"t","name":"n","type":"UInt64","is_in_primary_key":1}\n'
            return httpx.Response(200, text=line)
        import json

        return httpx.Response(200, text="".join(json.dumps(r) + "\n" for r in rows))

    config = ClickHouseSource.validate_config(
        {"url": "http://ch:8123", "database": "d`b", "cursor_columns": {"t": "n"}}
    )
    src = ClickHouseSource(
        config,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ch:8123"),
    )
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )
    items = [i async for i in src.read(configured)]

    assert items[-1] == State(stream="t", data={"cursor": "11"})  # not "9"
    assert seen[-1] == "SELECT * FROM `d\\`b`.`t` ORDER BY `n` ASC"


# ---- end to end: a run that dies mid-stream resumes near where it stopped ---------------


class _Crashing(FakeSource):
    """An ordered stream of 10 rows that fails after row 7 on its first run."""

    runs = 0

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        type(self).runs += 1
        tracker = CursorTracker("a", state, ordered=True, checkpoint_every=2)
        for i in range(int(tracker.start or 0) + 1, 11):
            if type(self).runs == 1 and i == 8:
                raise ConnectionError("link dropped")
            checkpoint = tracker.observe(i)
            if checkpoint:
                yield checkpoint
            yield Record(stream="a", data={"id": i})
        if final := tracker.final_state():
            yield final


async def test_a_run_that_dies_mid_stream_resumes_from_its_last_checkpoint(
    registry: ConnectorRegistry,
) -> None:
    _Crashing.runs = 0
    registry.register(_Crashing, replace=True)
    catalog = ConfiguredCatalog.from_catalog(
        await _Crashing.from_config({}).discover(),
        sync_mode=SyncMode.INCREMENTAL,
        destination_sync_mode=DestinationSyncMode.APPEND,
    )
    conn = Connection(
        name="c",
        source_name="fake",
        source_config={},
        destination_name="memory",
        destination_config={},
        catalog=catalog,
    )
    runner = SyncRunner(registry, options=SyncOptions(batch_size=100))

    first = await runner.run(conn)
    assert first.status is JobStatus.FAILED
    saved = (await runner.state_store.load(conn.id)).get("a")["cursor"]
    # Checkpoints fall when a value is known to be complete: 1, 3, 5. Rows 6 and 7
    # were read but not yet written when the source failed.
    assert saved == 5
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == [1, 2, 3, 4, 5]

    second = await runner.run(conn)
    assert second.status is JobStatus.SUCCEEDED
    assert [r["id"] for r in InMemoryDestination.sink["a"]] == list(range(1, 11))
