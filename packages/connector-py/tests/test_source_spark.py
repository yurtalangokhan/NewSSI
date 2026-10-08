"""Spark source: the shared reader through a fake engine, plus both transport adapters."""

from __future__ import annotations

import datetime as dt
import decimal
from collections.abc import Iterator
from typing import Any

import pytest

from connector import ConfigValidationError, ConnectorCategory, SyncMode
from connector.sources.spark import (
    SparkConnectEngine,
    SparkSource,
    SparkTable,
    ThriftEngine,
    build_connect_url,
    parse_describe,
    sql_literal,
)
from tests.fake_api import read_all

ORDERS_COLUMNS = [
    ("id", "bigint"),
    ("total", "decimal(10,2)"),
    ("updated_at", "timestamp"),
    ("tags", "array<string>"),
    ("customer", "struct<name:string,vip:boolean>"),
    ("raw", "binary"),
    ("paid", "boolean"),
]
ORDERS_ROWS = [
    {
        "id": 1,
        "total": decimal.Decimal("9.50"),
        "updated_at": dt.datetime(2026, 1, 1, 10),
        "tags": ["a"],
        "customer": {"name": "Ann", "vip": True},
        "raw": bytearray(b"\x01"),
        "paid": True,
    },
    {
        "id": 2,
        "total": decimal.Decimal("3.25"),
        "updated_at": dt.datetime(2026, 1, 2, 10),
        "tags": [],
        "customer": None,
        "raw": None,
        "paid": False,
    },
    {
        "id": 3,
        "total": decimal.Decimal("1.00"),
        "updated_at": dt.datetime(2026, 1, 3, 10),
        "tags": ["b", "c"],
        "customer": {"name": "Cy", "vip": False},
        "raw": b"\xff",
        "paid": True,
    },
]


class FakeEngine:
    """Answers the SQL the source builds; keeps every statement for assertions."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False
        self.iterators_closed = 0

    def list_tables(self, database: str, only: set[str] | None = None) -> list[SparkTable]:
        assert database == "lake.sales"
        self.listed_only = only
        tables = [SparkTable("orders", ORDERS_COLUMNS), SparkTable("regions", [("code", "string")])]
        return [t for t in tables if only is None or t.name in only]

    def describe_query(self, sql: str) -> list[tuple[str, str]]:
        assert sql.startswith("SELECT")
        return [("day", "date"), ("revenue", "double")]

    def execute(self, sql: str) -> Iterator[dict[str, Any]]:
        norm = " ".join(sql.split())
        self.executed.append(norm)
        if norm == "SELECT 1 AS ok":
            rows: list[dict[str, Any]] = [{"ok": 1}]
        elif "`lake`.`sales`.`orders`" in norm:
            rows = [dict(r) for r in ORDERS_ROWS]
            if "WHERE `updated_at` > TIMESTAMP '" in norm:
                stamp = norm.split("TIMESTAMP '", 1)[1].split("'", 1)[0]
                rows = [r for r in rows if r["updated_at"].isoformat() > stamp]
            if "ORDER BY `updated_at` ASC" in norm:
                rows.sort(key=lambda r: r["updated_at"])
        elif "`lake`.`sales`.`regions`" in norm:
            rows = [{"code": "EU"}, {"code": "US"}]
        elif norm.startswith("SELECT * FROM (SELECT day"):
            rows = [
                {"day": dt.date(2026, 1, 1), "revenue": 10.0},
                {"day": dt.date(2026, 1, 2), "revenue": 20.0},
            ]
            if "WHERE `day` > DATE '" in norm:
                since = norm.split("DATE '", 1)[1].split("'", 1)[0]
                rows = [r for r in rows if r["day"].isoformat() > since]
        else:
            raise AssertionError(f"unexpected sql: {norm}")
        return self._rows(rows)

    def _rows(self, rows: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        try:
            yield from rows
        finally:
            self.iterators_closed += 1

    def close(self) -> None:
        self.closed = True


REVENUE_SQL = "SELECT day, sum(amount) AS revenue FROM lake.sales.payments GROUP BY day"


def _spark(engine: FakeEngine, **cfg: Any) -> SparkSource:
    base = {"host": "spark.test", "database": "lake.sales"}
    config = SparkSource.validate_config({**base, **cfg})
    return SparkSource(config, engine_factory=lambda c: engine)


async def test_discover_tables_and_query_streams() -> None:
    engine = FakeEngine()
    src = _spark(
        engine,
        queries={"daily_revenue": REVENUE_SQL},
        cursor_columns={"orders": "updated_at", "daily_revenue": "day"},
    )
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["orders", "regions", "daily_revenue"]
    orders = catalog.get("orders")
    props = orders.json_schema["properties"]
    assert props["id"] == {"type": "integer", "x-spark-type": "bigint"}
    assert props["total"]["type"] == "number" and props["tags"]["type"] == "array"
    assert props["customer"]["type"] == "object" and props["paid"]["type"] == "boolean"
    assert props["updated_at"] == {
        "type": "string",
        "format": "date-time",
        "x-spark-type": "timestamp",
    }
    assert orders.namespace == "lake.sales" and orders.default_cursor_field == ["updated_at"]
    assert catalog.get("regions").supported_sync_modes == [SyncMode.FULL_REFRESH]
    revenue = catalog.get("daily_revenue")
    assert revenue.json_schema["properties"]["day"]["format"] == "date"
    assert SyncMode.INCREMENTAL in revenue.supported_sync_modes

    engine = FakeEngine()
    only = _spark(engine, tables=["regions"])
    assert (await only.discover()).names() == ["regions"]
    assert engine.listed_only == {"regions"}  # the engine describes only the wanted tables


async def test_full_refresh_converts_values_and_closes_iterators() -> None:
    engine = FakeEngine()
    src = _spark(engine, fetch_size=2)
    async with src:
        records, states = await read_all(src, only=["orders", "regions"])
    first = records["orders"][0]
    assert first["total"] == 9.5 and first["updated_at"] == "2026-01-01T10:00:00"
    assert first["customer"] == {"name": "Ann", "vip": True} and first["raw"] == "01"
    assert records["orders"][1]["customer"] is None and records["orders"][2]["raw"] == "ff"
    assert [r["code"] for r in records["regions"]] == ["EU", "US"]
    assert states == {}
    assert engine.executed[0] == "SELECT * FROM `lake`.`sales`.`orders`"
    assert engine.iterators_closed == 2 and engine.closed


async def test_incremental_renders_typed_literal_and_wraps_queries() -> None:
    engine = FakeEngine()
    src = _spark(
        engine,
        queries={"daily_revenue": REVENUE_SQL},
        cursor_columns={"orders": "updated_at", "daily_revenue": "day"},
    )
    prior = {
        "orders": {"cursor": "2026-01-01T10:00:00"},
        "daily_revenue": {"cursor": "2026-01-01"},
    }
    records, states = await read_all(
        src, only=["orders", "daily_revenue"], incremental=True, state=prior
    )
    assert [r["id"] for r in records["orders"]] == [2, 3]
    assert [r["revenue"] for r in records["daily_revenue"]] == [20.0]
    assert engine.executed[0] == (
        "SELECT * FROM `lake`.`sales`.`orders` WHERE `updated_at` > TIMESTAMP '2026-01-01T10:00:00'"
        " ORDER BY `updated_at` ASC"
    )
    assert engine.executed[1] == (
        f"SELECT * FROM ({REVENUE_SQL}) AS q WHERE `day` > DATE '2026-01-01' ORDER BY `day` ASC"
    )
    assert states["orders"] == {"cursor": "2026-01-03T10:00:00"}
    assert states["daily_revenue"] == {"cursor": "2026-01-02"}


async def test_check_reports_engine_failure() -> None:
    def broken(config: Any) -> Any:
        raise ConnectionRefusedError("sc://spark.test:15002 refused")

    src = SparkSource(SparkSource.validate_config({"host": "spark.test"}), engine_factory=broken)
    result = await src.check()
    assert not result.ok and "refused" in (result.message or "")


def test_sql_literal_typing_and_escaping() -> None:
    assert sql_literal("O'Neil\\x", "string") == "'O''Neil\\\\x'"
    assert sql_literal("2026-01-01T10:00:00", "timestamp") == "TIMESTAMP '2026-01-01T10:00:00'"
    assert sql_literal("2026-01-01", "date") == "DATE '2026-01-01'"
    assert sql_literal("42", "bigint") == "42" and sql_literal(3.5, "double") == "3.5"
    assert sql_literal(dt.datetime(2026, 1, 1, 10), "") == "TIMESTAMP '2026-01-01 10:00:00'"
    assert sql_literal(dt.date(2026, 1, 1), "") == "DATE '2026-01-01'"
    assert sql_literal(True, "boolean") == "TRUE" and sql_literal(None, "int") == "NULL"
    with pytest.raises(ValueError):
        sql_literal("1; DROP TABLE x", "int")  # a numeric column never gets a string injected


def test_config_rules_url_builder_and_secrets() -> None:
    cfg = SparkSource.validate_config({"host": "spark.test", "token": "t", "use_ssl": True})
    assert build_connect_url(cfg) == "sc://spark.test:15002/;use_ssl=true;token=t"
    plain = SparkSource.validate_config({"host": "spark.test", "port": 15003})
    assert build_connect_url(plain) == "sc://spark.test:15003/"
    explicit = SparkSource.validate_config({"host": "x", "connect_url": "sc://a:1/;token=z"})
    assert build_connect_url(explicit) == "sc://a:1/;token=z"
    assert SparkSource.secret_fields() == {"connect_url", "token", "password"}
    assert SparkSource.definition.category is ConnectorCategory.WAREHOUSE
    with pytest.raises(ConfigValidationError):
        SparkSource.validate_config({"host": "h", "thrift_auth": "LDAP"})
    with pytest.raises(ConfigValidationError):
        SparkSource.validate_config({"host": "h", "tables": ["a"], "queries": {"a": "SELECT 1"}})


# ---------------------------------------------------------------------------
# transport adapters
# ---------------------------------------------------------------------------


class _FakeHiveCursor:
    def __init__(self, conn: _FakeHiveConnection) -> None:
        self._conn = conn
        self._rows: list[tuple[Any, ...]] = []
        self.description: list[tuple[Any, ...]] | None = None

    def execute(self, sql: str) -> None:
        self._conn.executed.append(sql)
        if sql.startswith("SHOW TABLES IN"):
            self._rows = [
                ("sales", "orders", False),
                ("sales", "tmp_view", True),
                ("sales", "regions", False),
            ]
        elif sql.startswith("DESCRIBE QUERY"):
            self._rows = [("n", "int", None)]
        elif sql.startswith("DESCRIBE"):
            self._rows = [
                ("id", "bigint", None),
                ("day", "date", "partition column"),
                ("", "", ""),
                ("# Partition Information", "", ""),
                ("# col_name", "data_type", "comment"),
                ("day", "date", None),
            ]
        else:
            self.description = [("orders.id", "BIGINT_TYPE"), ("orders.day", "DATE_TYPE")]
            self._rows = [
                (1, dt.date(2026, 1, 1)),
                (2, dt.date(2026, 1, 2)),
                (3, dt.date(2026, 1, 3)),
            ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows[:n], self._rows[n:]
        return rows

    def close(self) -> None:
        self._conn.cursors_closed += 1


class _FakeHiveConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.cursors_closed = 0

    def cursor(self) -> _FakeHiveCursor:
        return _FakeHiveCursor(self)


def test_thrift_engine_lists_describes_and_streams() -> None:
    config = SparkSource.validate_config({"host": "h", "transport": "thrift", "fetch_size": 2})
    conn = _FakeHiveConnection()
    engine = ThriftEngine(config, connection=conn)
    tables = engine.list_tables("sales", only={"orders"})
    assert tables == [
        SparkTable("orders", [("id", "bigint"), ("day", "date")])
    ]  # temp view skipped, regions not wanted: not described
    assert conn.executed == ["SHOW TABLES IN `sales`", "DESCRIBE `sales`.`orders`"]
    assert engine.describe_query("SELECT 1 AS n") == [("n", "int")]
    assert [t.name for t in engine.list_tables("sales")] == ["orders", "regions"]
    rows = list(engine.execute("SELECT * FROM `sales`.`orders`"))
    assert rows == [
        {"id": 1, "day": dt.date(2026, 1, 1)},
        {"id": 2, "day": dt.date(2026, 1, 2)},
        {"id": 3, "day": dt.date(2026, 1, 3)},
    ]  # 'orders.id' prefixes are stripped, fetched in chunks of fetch_size
    assert conn.cursors_closed == 7
    assert parse_describe([]) == []


class _FakeColumn:
    def __init__(self, name: str, data_type: str) -> None:
        self.name, self.dataType = name, data_type


class _FakeTable:
    def __init__(self, name: str, temporary: bool = False) -> None:
        self.name, self.isTemporary = name, temporary


class _FakeRow:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def asDict(self, recursive: bool = False) -> dict[str, Any]:  # noqa: N802 - pyspark API
        assert recursive
        return dict(self._data)


class _FakeField:
    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.dataType = type("T", (), {"simpleString": staticmethod(lambda: kind)})()


class _FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.schema = type("S", (), {"fields": [_FakeField("id", "int")]})()

    def toLocalIterator(self):  # noqa: N802, ANN201 - pyspark API
        return iter(_FakeRow(r) for r in self._rows)


class _FakeSparkSession:
    def __init__(self) -> None:
        self.stopped = False
        self.sql_calls: list[str] = []
        session = self

        class _Catalog:
            def listTables(self, database: str) -> list[_FakeTable]:  # noqa: N802
                assert database == "lake.sales"
                return [_FakeTable("orders"), _FakeTable("scratch", temporary=True)]

            def listColumns(self, table: str, database: str) -> list[_FakeColumn]:  # noqa: N802
                return [_FakeColumn("id", "bigint"), _FakeColumn("ts", "timestamp")]

        self.catalog = _Catalog()

        def sql(query: str) -> _FakeFrame:
            session.sql_calls.append(query)
            return _FakeFrame([{"id": 1}, {"id": 2}])

        self.sql = sql

    def stop(self) -> None:
        self.stopped = True


def test_connect_engine_uses_catalog_and_local_iterator() -> None:
    config = SparkSource.validate_config({"host": "h", "database": "lake.sales"})
    session = _FakeSparkSession()
    engine = SparkConnectEngine(config, session=session)
    assert engine.list_tables("lake.sales") == [
        SparkTable("orders", [("id", "bigint"), ("ts", "timestamp")])
    ]
    assert engine.describe_query("SELECT 1") == [("id", "int")]
    assert list(engine.execute("SELECT * FROM t")) == [{"id": 1}, {"id": 2}]
    engine.close()
    assert not session.stopped  # an injected session is never stopped by the engine
