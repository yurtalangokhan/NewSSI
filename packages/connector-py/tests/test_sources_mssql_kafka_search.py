"""MSSQL, Kafka, Elasticsearch and OpenSearch sources against fake clients."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import decimal
import json
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from connector import (
    ConfiguredCatalog,
    ConfigValidationError,
    ConnectorCategory,
    Record,
    State,
    SyncMode,
    SyncState,
)
from connector.sources import kafka as kafka_module
from connector.sources.elasticsearch import ElasticsearchSource
from connector.sources.kafka import KafkaSource, build_consumer_kwargs
from connector.sources.mssql import MssqlSource, build_connection_string
from connector.sources.opensearch import OpenSearchSource
from tests.fake_api import FakeApi, read_all

# ---------------------------------------------------------------------------
# MSSQL: a fake DB-API connection (pyodbc is blocking, so the fake is sync too)
# ---------------------------------------------------------------------------

MODIFIED = [
    dt.datetime(2026, 1, 1, 10, 0),
    dt.datetime(2026, 1, 2, 10, 0),
    dt.datetime(2026, 1, 3, 10, 0),
]
ORDERS = [
    (1, decimal.Decimal("9.50"), MODIFIED[0], uuid.UUID(int=1), b"\x01\x02", True),
    (2, decimal.Decimal("3.25"), MODIFIED[1], uuid.UUID(int=2), None, False),
    (3, decimal.Decimal("1.00"), MODIFIED[2], uuid.UUID(int=3), b"\xff", True),
]
ORDER_COLUMNS = ["Id", "Total", "ModifiedAt", "RowGuid", "Payload", "Active"]
COLUMNS = [
    ("dbo", "Orders", "Id", "int"),
    ("dbo", "Orders", "Total", "decimal"),
    ("dbo", "Orders", "ModifiedAt", "datetime2"),
    ("dbo", "Orders", "RowGuid", "uniqueidentifier"),
    ("dbo", "Orders", "Payload", "varbinary"),
    ("dbo", "Orders", "Active", "bit"),
    ("sales", "Regions", "Code", "nvarchar"),
]
PRIMARY_KEYS = [("dbo", "Orders", "Id"), ("sales", "Regions", "Code")]


class _FakeMssqlCursor:
    def __init__(self, db: _FakeMssqlConnection) -> None:
        self._db = db
        self._rows: list[tuple[Any, ...]] = []
        self.description: list[tuple[Any, ...]] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        norm = " ".join(sql.split())
        self._db.executed.append((norm, params))
        if norm.startswith("SELECT 1"):
            cols, rows = ["ok"], [(1,)]
        elif "INFORMATION_SCHEMA.COLUMNS" in norm:
            cols = ["table_schema", "table_name", "column_name", "data_type"]
            rows = [c for c in COLUMNS if c[0] in params]
        elif "KEY_COLUMN_USAGE" in norm:
            cols = ["table_schema", "table_name", "column_name"]
            rows = [k for k in PRIMARY_KEYS if k[0] in params]
        elif "[sales].[Regions]" in norm:
            cols, rows = ["Code"], [("EU",), ("US",)]
        else:
            assert norm.startswith("SELECT * FROM [dbo].[Orders]")
            cols, rows = ORDER_COLUMNS, list(ORDERS)
            if "WHERE [ModifiedAt] > ?" in norm:
                rows = [r for r in rows if r[2] > params[0]]
            if "ORDER BY [ModifiedAt] ASC" in norm:
                rows.sort(key=lambda r: r[2])
        self.description = [(c, None, None, None, None, None, None) for c in cols]
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, n: int) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows[:n], self._rows[n:]
        return rows

    def close(self) -> None:
        self._db.cursors_closed += 1


class _FakeMssqlConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.cursors_closed = 0
        self.closed = False

    def cursor(self) -> _FakeMssqlCursor:
        return _FakeMssqlCursor(self)

    def close(self) -> None:
        self.closed = True


def _mssql(**cfg: Any) -> tuple[MssqlSource, _FakeMssqlConnection]:
    conn = _FakeMssqlConnection()
    base = {"host": "sql.test", "database": "shop", "username": "u", "password": "p"}
    config = MssqlSource.validate_config({**base, **cfg})
    return MssqlSource(config, connect=lambda c: conn), conn


def test_mssql_connection_string_variants() -> None:
    plain = build_connection_string(
        MssqlSource.validate_config(
            {"host": "sql.test", "database": "shop", "username": "svc", "password": "p"}
        )
    )
    assert plain.startswith(
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=sql.test,1433;DATABASE=shop;"
    )
    assert "Encrypt=yes;TrustServerCertificate=no;" in plain and "UID=svc;PWD=p;" in plain

    integrated = build_connection_string(
        MssqlSource.validate_config(
            {
                "host": "h",
                "port": 1444,
                "database": "d",
                "encrypt": False,
                "trust_server_certificate": True,
            }
        )
    )
    assert "Trusted_Connection=yes" in integrated and "UID=" not in integrated
    assert "SERVER=h,1444;" in integrated and "Encrypt=no;TrustServerCertificate=yes;" in integrated

    quoted = build_connection_string(
        MssqlSource.validate_config(
            {
                "host": "h",
                "database": "d",
                "username": "u",
                "password": "p;a}b",
                "extra_connection_params": {"ApplicationIntent": "ReadOnly"},
            }
        )
    )
    assert "PWD={p;a}}b};" in quoted and quoted.endswith("ApplicationIntent=ReadOnly;")
    assert MssqlSource.secret_fields() == {"password"}


async def test_mssql_check_discover_and_full_refresh() -> None:
    src, conn = _mssql(schemas=["dbo", "sales"], fetch_size=2)
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["Orders", "sales.Regions"]
    orders = catalog.get("Orders")
    assert orders.namespace == "dbo" and orders.source_defined_primary_key == [["Id"]]
    assert orders.json_schema["properties"]["Total"] == {"type": "number"}
    assert orders.json_schema["properties"]["Active"] == {"type": "boolean"}
    assert orders.json_schema["properties"]["RowGuid"] == {"type": "string"}
    assert orders.supported_sync_modes == [SyncMode.FULL_REFRESH]
    assert catalog.get("sales.Regions").namespace == "sales"

    async with src:
        records, states = await read_all(src)
    first = records["Orders"][0]
    assert first["Total"] == 9.5 and first["ModifiedAt"] == "2026-01-01T10:00:00"
    assert first["RowGuid"] == str(uuid.UUID(int=1)) and first["Payload"] == "0102"
    assert records["Orders"][1]["Payload"] is None and records["Orders"][2]["Active"] is True
    assert [r["Code"] for r in records["sales.Regions"]] == ["EU", "US"]
    assert states == {} and conn.closed
    assert any(sql == "SELECT * FROM [sales].[Regions]" for sql, _ in conn.executed)


async def test_mssql_incremental_binds_cursor_and_emits_state() -> None:
    src, conn = _mssql(cursor_columns={"Orders": "ModifiedAt"}, tables=["Orders"])
    catalog = await src.discover()
    assert catalog.names() == ["Orders"]
    assert SyncMode.INCREMENTAL in catalog.get("Orders").supported_sync_modes
    prior = {"Orders": {"cursor": "2026-01-01T10:00:00"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [r["Id"] for r in records["Orders"]] == [2, 3]
    sql, params = conn.executed[-1]
    assert sql == "SELECT * FROM [dbo].[Orders] WHERE [ModifiedAt] > ? ORDER BY [ModifiedAt] ASC"
    assert params == (dt.datetime(2026, 1, 1, 10, 0),)  # bound as a datetime, not a string
    assert states["Orders"] == {"cursor": "2026-01-03T10:00:00"}


async def test_mssql_check_reports_connection_failure() -> None:
    def broken(config: Any) -> Any:
        raise OSError("login timeout expired")

    src = MssqlSource(MssqlSource.validate_config({"host": "h", "database": "d"}), connect=broken)
    result = await src.check()
    assert not result.ok and "login timeout" in (result.message or "")


# ---------------------------------------------------------------------------
# Kafka: a fake aiokafka consumer with manual assignment
# ---------------------------------------------------------------------------


class _Msg:
    def __init__(
        self,
        topic: str,
        partition: int,
        offset: int,
        value: bytes | None,
        key: bytes | None = None,
        headers: list | None = None,
        control: bool = False,
    ) -> None:
        self.topic, self.partition, self.offset = topic, partition, offset
        self.value, self.key, self.headers = value, key, headers or []
        self.timestamp = 1767312000000 + offset  # epoch millis
        self.control = control  # transaction marker: takes an offset, is never delivered


class FakeConsumer:
    def __init__(self, log: dict[tuple[str, int], list[_Msg]], begin: dict[tuple[str, int], int]):
        self.log, self.begin = log, begin
        self.started = self.stopped = False
        self.assigned: list[Any] = []
        self.positions: dict[Any, int] = {}
        self.late: list[_Msg] = []  # appended once the end offsets were captured
        self.getmany_calls = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def topics(self) -> set[str]:
        return {t for t, _ in self.log} | {"__consumer_offsets"}

    def partitions_for_topic(self, topic: str) -> set[int] | None:
        parts = {p for t, p in self.log if t == topic}
        return parts or None

    def assign(self, tps: list[Any]) -> None:
        self.assigned = list(tps)

    async def end_offsets(self, tps: list[Any]) -> dict[Any, int]:
        ends = {
            tp: max((m.offset for m in self.log[tp]), default=self.begin[tp] - 1) + 1 for tp in tps
        }
        for msg in self.late:
            self.log[(msg.topic, msg.partition)].append(msg)
        self.late = []
        return ends

    async def beginning_offsets(self, tps: list[Any]) -> dict[Any, int]:
        return {tp: self.begin[tp] for tp in tps}

    def seek(self, tp: Any, offset: int) -> None:
        self.positions[tp] = offset

    async def getmany(self, *tps: Any, timeout_ms: int, max_records: int) -> dict[Any, list[_Msg]]:
        self.getmany_calls += 1
        out: dict[Any, list[_Msg]] = {}
        for tp in tps:
            msgs = [m for m in self.log[tp] if m.offset >= self.positions[tp]][:max_records]
            if msgs:
                # Like aiokafka: control records move the position but are not delivered.
                self.positions[tp] = msgs[-1].offset + 1
                delivered = [m for m in msgs if not m.control]
                if delivered:
                    out[tp] = delivered
        return out

    async def position(self, tp: Any) -> int:
        return self.positions[tp]


def _cluster() -> FakeConsumer:
    log = {
        ("orders", 0): [
            _Msg("orders", 0, 0, b'{"id": 1}', key=b"k1", headers=[("source", b"web")]),
            _Msg("orders", 0, 1, b'{"id": 2}'),
            _Msg("orders", 0, 2, b"not json"),
        ],
        ("orders", 1): [_Msg("orders", 1, 5, b'{"id": 3}'), _Msg("orders", 1, 6, None)],
        ("audit", 0): [_Msg("audit", 0, 0, b"x")],
    }
    return FakeConsumer(log, begin={("orders", 0): 0, ("orders", 1): 5, ("audit", 0): 0})


def _kafka(consumer: FakeConsumer, **cfg: Any) -> KafkaSource:
    config = KafkaSource.validate_config({"bootstrap_servers": "k:9092", **cfg})
    return KafkaSource(config, consumer_factory=lambda c: consumer)


async def test_kafka_discover_by_pattern_and_check() -> None:
    consumer = _cluster()
    src = _kafka(consumer, topic_pattern="^ord")
    async with src:
        assert (await src.check()).ok
        assert (await src.discover()).names() == ["orders"]
    assert consumer.started and consumer.stopped
    missing = _kafka(_cluster(), topics=["orders", "nope"])
    result = await missing.check()
    assert not result.ok and "nope" in (result.message or "")
    assert not (await _kafka(_cluster(), topic_pattern="^zzz").check()).ok


async def test_kafka_first_run_reads_to_end_and_records_offsets() -> None:
    consumer = _cluster()
    src = _kafka(consumer, topics=["orders"])
    records, states = await read_all(src, incremental=True)
    msgs = records["orders"]
    assert [(m["partition"], m["offset"]) for m in msgs] == [(0, 0), (0, 1), (0, 2), (1, 5), (1, 6)]
    assert msgs[0]["value"] == {"id": 1} and msgs[0]["key"] == "k1"
    assert msgs[0]["headers"] == {"source": "web"}
    assert msgs[0]["timestamp"].startswith("2026-01-02T00:00:00")
    assert msgs[2]["value"] == "not json"  # invalid JSON falls back to text
    assert msgs[4]["value"] is None  # tombstone
    assert states["orders"] == {"offsets": {"0": 3, "1": 7}}
    assert [tp.partition for tp in consumer.assigned] == [0, 1]


async def test_kafka_resumes_from_state_clamps_to_retention_and_ignores_late_messages() -> None:
    consumer = _cluster()
    consumer.late = [_Msg("orders", 0, 3, b'{"id": 99}')]  # arrives after the snapshot
    src = _kafka(consumer, topics=["orders"])
    prior = {"orders": {"offsets": {"0": 2, "1": 1}}}  # partition 1 offset 1 is gone (retention)
    records, states = await read_all(src, incremental=True, state=prior)
    assert [(m["partition"], m["offset"]) for m in records["orders"]] == [(0, 2), (1, 5), (1, 6)]
    assert states["orders"] == {"offsets": {"0": 3, "1": 7}}  # 99 is left for the next run


async def test_kafka_latest_start_and_record_limit() -> None:
    latest = _kafka(_cluster(), topics=["orders"], start_from="latest")
    records, states = await read_all(latest, incremental=True)
    assert records == {} and states["orders"] == {"offsets": {"0": 3, "1": 7}}

    capped = _kafka(_cluster(), topics=["orders"], max_records_per_topic=2, max_poll_records=1)
    records, states = await read_all(capped, incremental=True)
    assert len(records["orders"]) == 2
    offsets = states["orders"]["offsets"]
    assert offsets["0"] + offsets["1"] == 2 + 5  # exactly two records consumed in total

    # The limit holds when one poll returns more than the limit over several partitions.
    capped = _kafka(_cluster(), topics=["orders"], max_records_per_topic=2, max_poll_records=10)
    records, states = await read_all(capped, incremental=True)
    assert len(records["orders"]) == 2
    offsets = states["orders"]["offsets"]
    assert offsets["0"] + offsets["1"] == 2 + 5


async def test_kafka_control_record_before_the_snapshot_end_closes_the_partition() -> None:
    # A transactional producer ends each batch with a control record the consumer never
    # delivers. Here it sits at the last offset before the snapshot, and the producer goes on
    # writing: the first message past the snapshot says the partition is read, so the run
    # ends with the offsets saved instead of polling until the idle timeout (or the job's).
    log = {
        ("tx", 0): [
            _Msg("tx", 0, 0, b'{"id": 1}'),
            _Msg("tx", 0, 1, b'{"id": 2}'),
            _Msg("tx", 0, 2, None, control=True),
        ]
    }
    consumer = FakeConsumer(log, begin={("tx", 0): 0})
    consumer.late = [_Msg("tx", 0, 3, b'{"id": 3}'), _Msg("tx", 0, 4, b'{"id": 4}')]
    src = _kafka(consumer, topics=["tx"], idle_timeout_seconds=0.2)
    records, states = await read_all(src, incremental=True)
    assert [m["offset"] for m in records["tx"]] == [0, 1]
    assert states["tx"] == {"offsets": {"0": 3}}
    assert consumer.getmany_calls == 1  # no polling past the first post-snapshot message


async def test_kafka_idle_partition_at_a_control_record_closes_by_consumer_position() -> None:
    # No producer activity after the control record: the consumer's own position (which
    # moved past the marker) tells that the end was reached.
    log = {("tx", 0): [_Msg("tx", 0, 0, b'{"id": 1}'), _Msg("tx", 0, 1, None, control=True)]}
    consumer = FakeConsumer(log, begin={("tx", 0): 0})
    src = _kafka(consumer, topics=["tx"], idle_timeout_seconds=0.2)
    records, states = await read_all(src, incremental=True)
    assert [m["offset"] for m in records["tx"]] == [0]
    assert states["tx"] == {"offsets": {"0": 2}}
    assert consumer.getmany_calls == 2


async def test_kafka_checkpoints_mid_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kafka_module, "CHECKPOINT_RECORDS", 2)
    src = _kafka(_cluster(), topics=["orders"], max_poll_records=10)
    catalog = ConfiguredCatalog.from_catalog(await src.discover(), sync_mode=SyncMode.INCREMENTAL)
    items = [item async for item in src.read(catalog, SyncState())]
    kinds = ["R" if isinstance(item, Record) else "S" for item in items]
    assert kinds == ["R", "R", "S", "R", "R", "S", "R", "S"]
    states = [item.data["offsets"] for item in items if isinstance(item, State)]
    assert states == [{"0": 2, "1": 5}, {"0": 3, "1": 6}, {"0": 3, "1": 7}]


async def test_kafka_saved_offset_past_the_end_restarts_the_partition() -> None:
    # The topic was recreated: offsets start over, the saved one lies beyond the new end.
    consumer = _cluster()
    src = _kafka(consumer, topics=["orders"])
    prior = {"orders": {"offsets": {"0": 50, "1": 7}}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [(m["partition"], m["offset"]) for m in records["orders"]] == [(0, 0), (0, 1), (0, 2)]
    assert states["orders"] == {"offsets": {"0": 3, "1": 7}}


async def test_kafka_missing_timestamp_is_null() -> None:
    consumer = _cluster()
    consumer.log[("audit", 0)][0].timestamp = -1  # CreateTime unavailable (old message format)
    records, _ = await read_all(_kafka(consumer, topics=["audit"]))
    assert records["audit"][0]["timestamp"] is None


async def test_kafka_base64_values_and_full_refresh_has_no_state() -> None:
    src = _kafka(_cluster(), topics=["audit"], value_format="base64", key_format="base64")
    records, states = await read_all(src)
    assert records["audit"][0]["value"] == base64.b64encode(b"x").decode()
    assert records["audit"][0]["key"] is None and states == {}


def test_kafka_config_rules_and_consumer_kwargs() -> None:
    with pytest.raises(ConfigValidationError):
        KafkaSource.validate_config({"bootstrap_servers": "k:9092"})
    with pytest.raises(ConfigValidationError):
        KafkaSource.validate_config(
            {"bootstrap_servers": "k:9092", "topics": ["t"], "security_protocol": "SASL_SSL"}
        )
    cfg = KafkaSource.validate_config(
        {
            "bootstrap_servers": "k:9092",
            "topics": ["t"],
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "SCRAM-SHA-512",
            "sasl_username": "u",
            "sasl_password": "p",
        }
    )
    kwargs = build_consumer_kwargs(cfg)
    assert kwargs["group_id"] is None and kwargs["enable_auto_commit"] is False
    assert kwargs["sasl_mechanism"] == "SCRAM-SHA-512" and kwargs["sasl_plain_password"] == "p"
    assert kwargs["ssl_context"].check_hostname is True
    assert "ssl_context" not in build_consumer_kwargs(
        KafkaSource.validate_config({"bootstrap_servers": "k:9092", "topics": ["t"]})
    )
    assert KafkaSource.secret_fields() == {"sasl_password"}
    assert KafkaSource.definition.category is ConnectorCategory.STREAMING


# ---------------------------------------------------------------------------
# Elasticsearch / OpenSearch
# ---------------------------------------------------------------------------

MAPPINGS = {
    "orders": {
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "total": {"type": "float"},
                "qty": {"type": "long"},
                "customer": {
                    "properties": {"name": {"type": "keyword"}, "vip": {"type": "boolean"}}
                },
                "tags": {"type": "keyword"},
                "lines": {
                    "type": "nested",
                    "properties": {"sku": {"type": "keyword"}, "qty": {"type": "long"}},
                },
            }
        }
    },
    "logs-2026": {
        "mappings": {"_doc": {"properties": {"message": {"type": "text"}}}}
    },  # ES 6 layout
    ".kibana": {"mappings": {"properties": {"type": {"type": "keyword"}}}},
}
DOCS = [
    {
        "_index": "orders",
        "_id": "a",
        "_source": {"@timestamp": "2026-01-01T00:00:00Z", "total": 1.5},
    },
    {
        "_index": "orders",
        "_id": "b",
        "_source": {"@timestamp": "2026-01-02T00:00:00Z", "total": 2.5},
    },
    {
        "_index": "orders",
        "_id": "c",
        "_source": {"@timestamp": "2026-01-03T00:00:00Z", "total": 3.5},
    },
]


class _SearchApi(FakeApi):
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.cleared: list[Any] = []
        super().__init__(
            {
                "/": {"name": "node-1", "version": {"number": "8.13.0"}},
                "/*/_mapping": MAPPINGS,
                "/orders,logs-*/_mapping": {k: v for k, v in MAPPINGS.items() if k != ".kibana"},
                "POST /orders/_search": self._search,
                "POST /logs-2026/_search": lambda r: {"hits": {"hits": []}},
                "POST /_search/scroll": self._scroll,
                "DELETE /_search/scroll": self._clear,
            }
        )

    def _matching(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        docs = DOCS
        for clause in ((body.get("query") or {}).get("bool") or {}).get("filter") or []:
            if "range" in clause:
                since = clause["range"]["@timestamp"]["gt"]
                docs = [d for d in docs if d["_source"]["@timestamp"] > since]
        return docs

    def _search(self, request: httpx.Request) -> dict[str, Any]:
        assert request.url.params["scroll"] == "5m"
        body = json.loads(request.content)
        self.bodies.append(body)
        docs = self._matching(body)
        size = body["size"]
        self._pending = docs[size:]
        return {"_scroll_id": "s1", "hits": {"hits": docs[:size]}}

    def _scroll(self, request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        assert body == {"scroll": "5m", "scroll_id": "s1"}
        page, self._pending = self._pending[:1], self._pending[1:]
        return {"_scroll_id": "s1", "hits": {"hits": page}}

    def _clear(self, request: httpx.Request) -> dict[str, Any]:
        self.cleared.append(json.loads(request.content)["scroll_id"])
        return {"succeeded": True}


def _es(api: _SearchApi, cls: type = ElasticsearchSource, **cfg: Any) -> Any:
    config = cls.validate_config({"url": "https://es.test:9200", **cfg})
    return cls(config, client=api.client("https://es.test:9200"))


async def test_elasticsearch_discover_maps_types_and_resolves_cursor() -> None:
    src = _es(_SearchApi(), cursor_field="@timestamp", cursor_fields={"logs-2026": "message"})
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["logs-2026", "orders"]  # .kibana skipped
    orders = catalog.get("orders")
    props = orders.json_schema["properties"]
    assert props["@timestamp"] == {"type": "string", "format": "date-time"}
    assert props["total"] == {"type": "number"} and props["qty"] == {"type": "integer"}
    assert props["customer"] == {
        "type": "object",
        "properties": {"name": {"type": "string"}, "vip": {"type": "boolean"}},
    }
    assert orders.default_cursor_field == ["@timestamp"] and orders.source_defined_primary_key == [
        ["_id"]
    ]
    logs = catalog.get("logs-2026")
    assert logs.json_schema["properties"] == {  # typed ES 6 mapping; _id/_index ride on every hit
        "message": {"type": "string"},
        "_id": {"type": "string"},
        "_index": {"type": "string"},
    }
    assert logs.default_cursor_field == ["message"]  # explicit override wins

    restricted = _es(_SearchApi(), indices=["orders", "logs-*"], cursor_field="@timestamp")
    assert (await restricted.discover()).names() == ["logs-2026", "orders"]
    no_cursor = _es(_SearchApi(), cursor_field="updated_at")
    assert (await no_cursor.discover()).get("orders").supported_sync_modes == [
        SyncMode.FULL_REFRESH
    ]


async def test_elasticsearch_scrolls_all_pages_and_clears_the_scroll() -> None:
    api = _SearchApi()
    src = _es(
        api, page_size=1, include_fields=["total", "@timestamp"], query={"term": {"tags": "x"}}
    )
    records, states = await read_all(src, only=["orders"])
    assert [r["_id"] for r in records["orders"]] == ["a", "b", "c"]
    assert records["orders"][0] == {
        "@timestamp": "2026-01-01T00:00:00Z",
        "total": 1.5,
        "_id": "a",
        "_index": "orders",
    }
    assert states == {}
    body = api.bodies[0]
    assert body["sort"] == ["_doc"] and body["_source"] == {"includes": ["total", "@timestamp"]}
    assert body["query"] == {"bool": {"filter": [{"term": {"tags": "x"}}]}}
    assert api.cleared == [["s1"]]
    assert len(api.calls("/_search/scroll")) == 4  # 2 pages + 1 empty + 1 delete


async def test_elasticsearch_incremental_range_filter_and_state() -> None:
    api = _SearchApi()
    src = _es(api, cursor_field="@timestamp")
    prior = {"orders": {"cursor": "2026-01-01T12:00:00+00:00"}}
    records, states = await read_all(src, only=["orders"], incremental=True, state=prior)
    assert [r["_id"] for r in records["orders"]] == ["b", "c"]
    # The cursor is kept as normalised ISO-8601: ``format`` says so, whatever date format
    # the index mapping uses (``yyyy-MM-dd HH:mm:ss``, ``epoch_second`` ...).
    assert api.bodies[0]["query"]["bool"]["filter"] == [
        {
            "range": {
                "@timestamp": {
                    "gt": "2026-01-01T12:00:00+00:00",
                    "format": "strict_date_optional_time||epoch_millis",
                }
            }
        }
    ]
    assert states["orders"] == {"cursor": "2026-01-03T00:00:00+00:00"}

    # A numeric cursor (a sequence field) is passed as it is; ``format`` is a date thing.
    body = src._search_body("seq", 7)
    assert body["query"]["bool"]["filter"] == [{"range": {"seq": {"gt": 7}}}]


def test_elasticsearch_auth_headers() -> None:
    raw = _es(_SearchApi(), api_key="id1:secret1").auth_headers()
    assert raw == {"Authorization": "ApiKey " + base64.b64encode(b"id1:secret1").decode()}
    encoded = _es(_SearchApi(), api_key="aWQxOnNlY3JldDE=").auth_headers()
    assert encoded == {"Authorization": "ApiKey aWQxOnNlY3JldDE="}
    basic = _es(_SearchApi(), username="elastic", password="pw").auth_headers()
    assert basic == {"Authorization": "Basic " + base64.b64encode(b"elastic:pw").decode()}
    assert _es(_SearchApi()).auth_headers() == {}
    assert ElasticsearchSource.secret_fields() == {"password", "api_key"}


async def test_opensearch_reuses_the_reader_with_its_own_config() -> None:
    api = _SearchApi()
    src = _es(api, OpenSearchSource, username="admin", password="pw", cursor_field="@timestamp")
    assert isinstance(src, ElasticsearchSource)
    assert OpenSearchSource.definition.name == "opensearch"
    assert OpenSearchSource.definition.category is ConnectorCategory.SEARCH_ENGINE
    assert "api_key" not in OpenSearchSource.spec().connection_specification["properties"]
    assert OpenSearchSource.secret_fields() == {"password"}
    records, states = await read_all(src, only=["orders"], incremental=True)
    assert [r["_id"] for r in records["orders"]] == ["a", "b", "c"]
    assert states["orders"]["cursor"] == "2026-01-03T00:00:00+00:00"
    assert api.requests[0].headers["Authorization"].startswith("Basic ")


async def test_elasticsearch_nested_fields_are_arrays_of_objects() -> None:
    # Live 8.19: a nested mapping with properties was declared "object" while every hit
    # carried a list; the "properties" branch ran before the type lookup.
    props = (await _es(_SearchApi()).discover()).get("orders").json_schema["properties"]
    assert props["lines"] == {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"sku": {"type": "string"}, "qty": {"type": "integer"}},
        },
    }
    assert props["_id"] == {"type": "string"} and props["_index"] == {"type": "string"}


class _LazyMetadataConsumer(FakeConsumer):
    """aiokafka 0.14 without a subscription or group: the consumer's own cluster view
    holds no topic until the client fetched all metadata, and ``assign`` narrows it."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.metadata_fetches = 0
        self._client = SimpleNamespace(fetch_all_metadata=self._fetch_all_metadata)

    async def _fetch_all_metadata(self) -> Any:
        self.metadata_fetches += 1
        log = self.log
        return SimpleNamespace(
            partitions_for_topic=lambda topic: {p for t, p in log if t == topic} or None
        )

    def partitions_for_topic(self, topic: str) -> set[int] | None:
        return None


async def test_kafka_reads_partitions_from_a_metadata_snapshot_when_the_consumer_has_none() -> None:
    # Live Kafka 4.3 + aiokafka 0.14: partitions_for_topic answered None for populated
    # topics, so read() skipped every topic and delivered nothing.
    seed = _cluster()
    consumer = _LazyMetadataConsumer(seed.log, begin=seed.begin)
    src = _kafka(consumer, topics=["orders", "audit"])
    records, states = await read_all(src, incremental=True)
    assert [(m["partition"], m["offset"]) for m in records["orders"]] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 5),
        (1, 6),
    ]
    assert [m["offset"] for m in records["audit"]] == [0]
    assert states["orders"] == {"offsets": {"0": 3, "1": 7}}
    assert consumer.metadata_fetches == 1  # one snapshot per read, not one per topic


async def test_kafka_close_swallows_the_spurious_cancellation_of_an_idle_consumer() -> None:
    # aiokafka 0.14: a consumer that never polled cancels its own coordinator task in
    # stop() and lets the CancelledError out; the runner then stored the job as cancelled.
    class CancellingStop(FakeConsumer):
        async def stop(self) -> None:
            self.stopped = True
            raise asyncio.CancelledError

    seed = _cluster()
    consumer = CancellingStop(seed.log, begin=seed.begin)
    src = _kafka(consumer, topics=["orders"])
    await src._get_consumer()
    await src.close()  # must not raise
    assert consumer.stopped and src._consumer is None


async def test_kafka_close_still_propagates_a_real_cancellation() -> None:
    class HangingStop(FakeConsumer):
        async def stop(self) -> None:
            await asyncio.Event().wait()

    seed = _cluster()
    src = _kafka(HangingStop(seed.log, begin=seed.begin), topics=["orders"])
    await src._get_consumer()
    task = asyncio.create_task(src.close())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
