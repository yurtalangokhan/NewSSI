"""MySQL and MongoDB sources exercised through injected fake clients (no drivers needed)."""

from __future__ import annotations

import datetime as dt
import decimal
from typing import Any

import pytest

from connector import ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.sources.mongodb import MongoDbSource
from connector.sources.mysql import MySqlSource

# ---------------------------------------------------------------------------
# MySQL fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], columns: list[dict[str, Any]]):
        self._tables = tables
        self._columns = columns
        self._rows: list[dict[str, Any]] = []
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False

    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        # Like aiomysql's SSCursor: closing reads whatever is left of the result set.
        self._rows = []
        self.closed = True

    async def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, args))
        norm = " ".join(sql.split())
        if norm.startswith("SELECT 1"):
            self._rows = [{"ok": 1}]
        elif "information_schema.COLUMNS" in norm:
            self._rows = list(self._columns)
        else:
            table = norm.split("`")[1]
            rows = list(self._tables[table])
            if "WHERE" in norm:
                col = norm.split("WHERE `")[1].split("`")[0]
                rows = [r for r in rows if r[col] > args[0]]
            if "ORDER BY" in norm:
                col = norm.split("ORDER BY `")[1].split("`")[0]
                rows.sort(key=lambda r: r[col])
            self._rows = rows

    async def fetchall(self) -> list[dict[str, Any]]:
        rows, self._rows = self._rows, []
        return rows

    async def fetchmany(self, n: int) -> list[dict[str, Any]]:
        rows, self._rows = self._rows[:n], self._rows[n:]
        return rows


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False

    def cursor(self, *args: Any) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._conn = _FakeConn(cursor)
        self.closed = False

    def acquire(self):  # noqa: ANN201
        conn = self._conn

        class _Ctx:
            async def __aenter__(self_inner):  # noqa: ANN204, N805
                return conn

            async def __aexit__(self_inner, *exc: object) -> None:  # noqa: N805
                return None

        return _Ctx()


def _mysql_source(rows: list[dict[str, Any]], cursor_col: str | None = None) -> MySqlSource:
    cursor = _FakeCursor(
        tables={"orders": rows},
        columns=[
            {"table_name": "orders", "column_name": "id", "data_type": "int", "column_key": "PRI"},
            {
                "table_name": "orders",
                "column_name": "total",
                "data_type": "decimal",
                "column_key": "",
            },
            {
                "table_name": "orders",
                "column_name": "updated_at",
                "data_type": "datetime",
                "column_key": "",
            },
        ],
    )
    cfg = MySqlSource.validate_config(
        {
            "host": "h",
            "database": "shop",
            "username": "u",
            "password": "p",
            "fetch_size": 2,
            "cursor_columns": {"orders": cursor_col} if cursor_col else {},
        }
    )
    return MySqlSource(cfg, pool=_FakePool(cursor))


_MYSQL_ROWS = [
    {"id": 1, "total": decimal.Decimal("9.50"), "updated_at": dt.datetime(2026, 1, 1, 10)},
    {"id": 2, "total": decimal.Decimal("3.25"), "updated_at": dt.datetime(2026, 1, 2, 10)},
    {"id": 3, "total": decimal.Decimal("1.00"), "updated_at": dt.datetime(2026, 1, 3, 10)},
]


async def test_mysql_check_discover_full_refresh() -> None:
    src = _mysql_source(_MYSQL_ROWS)
    assert (await src.check()).ok
    catalog = await src.discover()
    stream = catalog.get("orders")
    assert stream is not None and stream.namespace == "shop"
    assert stream.json_schema["properties"]["total"] == {"type": "number"}
    assert stream.source_defined_primary_key == [["id"]]
    assert stream.supported_sync_modes == [SyncMode.FULL_REFRESH]

    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    assert all(isinstance(i, Record) for i in items)
    assert [i.data["total"] for i in items] == [9.5, 3.25, 1.0]  # Decimal -> float
    assert items[0].data["updated_at"] == "2026-01-01T10:00:00"  # datetime -> ISO


async def test_mysql_incremental_uses_where_and_emits_state() -> None:
    src = _mysql_source(_MYSQL_ROWS, cursor_col="id")
    catalog = await src.discover()
    assert SyncMode.INCREMENTAL in catalog.get("orders").supported_sync_modes
    configured = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL)
    items = [i async for i in src.read(configured, SyncState(streams={"orders": {"cursor": 1}}))]
    records = [i for i in items if isinstance(i, Record)]
    assert [r.data["id"] for r in records] == [2, 3]
    assert items[-1] == State(stream="orders", data={"cursor": 3})


async def test_mysql_early_exit_drops_the_connection_instead_of_draining_the_cursor() -> None:
    # A preview reads a few rows and stops. Closing aiomysql's streaming cursor would read
    # the rest of the table off the socket first; the connection is dropped instead.
    src = _mysql_source(_MYSQL_ROWS)
    pool: Any = src._pool
    cursor, conn = pool._conn._cursor, pool._conn
    catalog = await src.discover()  # the fake hands out one cursor; discovery closed it
    cursor.closed = False
    items = src.read(ConfiguredCatalog.from_catalog(catalog))
    assert isinstance(await anext(items), Record)
    await items.aclose()
    assert conn.closed and not cursor.closed

    # Read to the end, the cursor is closed and the connection goes back to the pool.
    src = _mysql_source(_MYSQL_ROWS)
    pool = src._pool
    cursor, conn = pool._conn._cursor, pool._conn
    assert len([i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]) == 3
    assert cursor.closed and not conn.closed


async def test_mysql_masks_password_in_spec() -> None:
    assert "password" in MySqlSource.secret_fields()
    masked = MySqlSource.mask_config({"host": "h", "password": "p"})
    assert masked["password"] == "********"


# ---------------------------------------------------------------------------
# MongoDB fakes
# ---------------------------------------------------------------------------


class _FakeFind:
    def __init__(self, docs: list[dict[str, Any]], query: dict[str, Any], limit: int | None):
        self._docs = docs
        self._query = query
        self._limit = limit
        self._sort: tuple[str, int] | None = None

    def sort(self, field: str, direction: int) -> _FakeFind:
        self._sort = (field, direction)
        return self

    def __aiter__(self):  # noqa: ANN204
        docs = list(self._docs)
        for field, cond in self._query.items():
            if isinstance(cond, dict) and "$gt" in cond:
                docs = [d for d in docs if d.get(field) is not None and d[field] > cond["$gt"]]
        if self._sort:
            f, d = self._sort
            docs.sort(key=lambda x: _dotted(x, f), reverse=d < 0)
        if self._limit:
            docs = docs[: self._limit]

        async def gen():  # noqa: ANN202
            for doc in docs:
                yield dict(doc)

        return gen()


def _dotted(doc: dict[str, Any], path: str) -> Any:
    value: Any = doc
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.calls: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any], **kwargs: Any) -> _FakeFind:
        self.calls.append({"query": query, **kwargs})
        return _FakeFind(self._docs, query, kwargs.get("limit"))


class _FakeDb:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self._cols = {k: _FakeCollection(v) for k, v in collections.items()}
        self.pinged = False

    async def command(self, name: str) -> dict[str, Any]:
        self.pinged = True
        return {"ok": 1}

    async def list_collection_names(self) -> list[str]:
        return list(self._cols)

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._cols[name]


class _FakeClient:
    def __init__(self, db: _FakeDb) -> None:
        self._db = db

    def __getitem__(self, name: str) -> _FakeDb:
        return self._db


class _Oid:
    """Stands in for bson.ObjectId: str() gives the hex, ordering by that hex."""

    def __init__(self, hex_: str) -> None:
        self.hex = hex_

    def __str__(self) -> str:
        return self.hex

    def __lt__(self, other: _Oid) -> bool:
        return self.hex < other.hex

    def __gt__(self, other: _Oid) -> bool:
        return self.hex > other.hex


_MONGO_DOCS = [
    {"_id": _Oid("a1"), "name": "x", "tags": ["t"], "updatedAt": dt.datetime(2026, 1, 1)},
    {"_id": _Oid("a2"), "name": "y", "tags": [], "updatedAt": dt.datetime(2026, 1, 2)},
    {"_id": _Oid("a3"), "name": "z", "tags": ["u"], "updatedAt": dt.datetime(2026, 1, 3)},
]


def _mongo_source(cursor_field: str | None = None) -> tuple[MongoDbSource, _FakeDb]:
    db = _FakeDb({"users": _MONGO_DOCS, "system.views": [], "empty": []})
    cfg = MongoDbSource.validate_config(
        {
            "connection_string": "mongodb://u:p@h/",
            "database": "app",
            "cursor_fields": {"users": cursor_field} if cursor_field else {},
        }
    )
    return MongoDbSource(cfg, client=_FakeClient(db)), db


async def test_mongo_check_discover_and_conversion() -> None:
    src, db = _mongo_source()
    assert (await src.check()).ok and db.pinged
    catalog = await src.discover()
    assert catalog.names() == ["empty", "users"]  # system.* excluded
    users = catalog.get("users")
    assert users.json_schema["properties"]["tags"] == {"type": "array"}
    assert users.source_defined_primary_key == [["_id"]]

    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog, only=["users"]))]
    assert [i.data["_id"] for i in items] == ["a1", "a2", "a3"]  # ObjectId -> str
    assert items[0].data["updatedAt"] == "2026-01-01T00:00:00"


async def test_mongo_incremental_filters_and_sorts() -> None:
    src, db = _mongo_source(cursor_field="updatedAt")
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["users"]
    )
    prior = SyncState(streams={"users": {"cursor": "2026-01-01T00:00:00"}})
    items = [i async for i in src.read(configured, prior)]
    records = [i for i in items if isinstance(i, Record)]
    assert [r.data["name"] for r in records] == ["y", "z"]
    assert items[-1] == State(stream="users", data={"cursor": "2026-01-03T00:00:00"})
    last_call = db["users"].calls[-1]
    assert last_call["query"] == {"updatedAt": {"$gt": dt.datetime(2026, 1, 1)}}
    assert last_call["batch_size"] == 500


async def test_mongo_dotted_cursor_field_is_read_from_the_nested_document() -> None:
    docs = [
        {"_id": _Oid("b1"), "meta": {"updatedAt": dt.datetime(2026, 1, 1)}},
        {"_id": _Oid("b2"), "meta": {"updatedAt": dt.datetime(2026, 1, 2)}},
    ]
    db = _FakeDb({"events": docs})
    cfg = MongoDbSource.validate_config(
        {
            "connection_string": "mongodb://u:p@h/",
            "database": "app",
            "cursor_fields": {"events": "meta.updatedAt"},
        }
    )
    src = MongoDbSource(cfg, client=_FakeClient(db))
    configured = ConfiguredCatalog.from_catalog(
        await src.discover(), sync_mode=SyncMode.INCREMENTAL
    )
    items = [i async for i in src.read(configured)]
    assert items[-1] == State(stream="events", data={"cursor": "2026-01-02T00:00:00"})


async def test_mongo_saves_a_text_cursor_only_at_the_end_of_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("connector.sources.mongodb.CHECKPOINT_ROWS", 1)

    async def states(cursor_field: str) -> list[Any]:
        src, _ = _mongo_source(cursor_field=cursor_field)
        configured = ConfiguredCatalog.from_catalog(
            await src.discover(), sync_mode=SyncMode.INCREMENTAL, only=["users"]
        )
        return [
            i.data["cursor"]
            for i in [i async for i in src.read(configured)]
            if isinstance(i, State)
        ]

    # A collection's collation may call two different strings equal, so "every document
    # with this value has been read" cannot be decided from the text.
    assert await states("name") == ["z"]
    # Dates are compared the way the server sorts them: saved along the way.
    assert await states("updatedAt") == [
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
        "2026-01-03T00:00:00",
    ]


def test_mongo_connection_string_is_secret() -> None:
    assert MongoDbSource.secret_fields() == {"connection_string"}


async def test_mysql_json_and_bit_columns_are_declared_and_decoded_as_json_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Live MySQL 8.4: pymysql has no decoder for JSON (the text arrived as a string
    # against a declared "object") nor for BIT (raw bytes, hex-encoded on the way out).
    from types import SimpleNamespace

    from connector.sources import mysql as module

    created: dict[str, Any] = {}

    async def create_pool(**kwargs: Any) -> str:
        created.update(kwargs)
        return "pool"

    fakes = {
        "aiomysql": SimpleNamespace(create_pool=create_pool),
        "pymysql.converters": SimpleNamespace(decoders={1: int}),
        "pymysql.constants": SimpleNamespace(FIELD_TYPE=SimpleNamespace(JSON=245, BIT=16)),
    }
    monkeypatch.setattr(module, "require_extra", lambda name, **_: fakes[name])
    cfg = MySqlSource.validate_config(
        {"host": "h", "database": "shop", "username": "u", "password": "p"}
    )
    src = MySqlSource(cfg)

    assert await src._get_pool() == "pool"
    conv = created["conv"]
    assert conv[1] is int  # pymysql's own decoders are kept
    assert conv[245]('{"n": 1, "tags": ["a"]}') == {"n": 1, "tags": ["a"]}
    assert conv[16](bytes([1])) == 1 and conv[16](bytes([1, 0])) == 256

    cursor = _FakeCursor(
        {"flags": []},
        [
            {"table_name": "flags", "column_name": "attrs", "data_type": "json", "column_key": ""},
            {"table_name": "flags", "column_name": "flag", "data_type": "bit", "column_key": ""},
        ],
    )
    catalog = await MySqlSource(cfg, pool=_FakePool(cursor)).discover()
    props = catalog.get("flags").json_schema["properties"]
    assert props["attrs"] == {"type": "object"}
    assert props["flag"] == {"type": "integer"}  # BIT(n) is a bit field; BIT(1) yields 0/1


async def test_mongo_schema_inference_sees_the_json_values_the_records_carry() -> None:
    # Live MongoDB 8: a Decimal128 amount was declared "string" (inferred from the raw
    # BSON value) while every record carried a float.
    class Decimal128:
        def __init__(self, text: str) -> None:
            self._text = text

        def to_decimal(self) -> decimal.Decimal:
            return decimal.Decimal(self._text)

    docs = [
        {
            "_id": _Oid("c1"),
            "amount": Decimal128("0.25"),
            "when": dt.datetime(2026, 1, 1),
            "n": {"d": Decimal128("1.5")},
        }
    ]
    cfg = MongoDbSource.validate_config(
        {"connection_string": "mongodb://u:p@h/", "database": "app"}
    )
    src = MongoDbSource(cfg, client=_FakeClient(_FakeDb({"payments": docs})))

    catalog = await src.discover()
    props = catalog.get("payments").json_schema["properties"]
    [record] = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]

    assert props["amount"] == {"type": "number"} and record.data["amount"] == 0.25
    assert props["_id"] == {"type": "string"} and record.data["_id"] == "c1"
    assert props["when"]["type"] == "string" and record.data["when"] == "2026-01-01T00:00:00"
    assert props["n"] == {"type": "object"} and record.data["n"] == {
        "d": 1.5
    }  # inference stays top-level
