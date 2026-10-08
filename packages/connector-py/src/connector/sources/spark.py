"""Apache Spark source: tables and ad-hoc SQL of a Spark cluster, read remotely.

Two transports reach the cluster without running Spark in this process:

* ``connect`` - Spark Connect (gRPC, Spark 3.4+). Needs the ``spark`` extra
  (``pyspark[connect]``; on Spark 4 the slim ``pyspark-client`` package works too).
* ``thrift``  - Spark Thrift Server, the HiveServer2 protocol behind JDBC/ODBC.
  Needs the ``spark-thrift`` extra (pyhive with pure-sasl).

Every table of ``database`` becomes a stream; ``queries`` adds streams backed by
arbitrary Spark SQL. Incremental sync uses ``cursor_columns`` with a
``WHERE col > <last>`` predicate (queries are wrapped as a subquery) and an
``ORDER BY`` on the cursor, so Spark sorts the result - fine for change
columns that are indexed or partitioned, costly on very large unsorted tables.
Rows are pulled lazily in ``fetch_size`` chunks; the Spark client libraries are
blocking, so every call runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Callable, Collection, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from ..base import BaseSource, secret_field, sensitive_mapping_field
from ..common.blocking import iterate_in_thread
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.tabular import CHECKPOINT_ROWS, is_exact_cursor, table_stream
from ..common.tabular import backtick_ident as _ident
from ..common.tabular import to_json_value as _to_json
from ..extras import require_extra
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

SPARK_TYPE_KEY = "x-spark-type"

_INTEGER_PREFIXES = ("int", "bigint", "smallint", "tinyint", "long", "short", "byte")
_NUMBER_PREFIXES = ("double", "float", "decimal")


class SparkConfig(BaseModel):
    transport: Literal["connect", "thrift"] = Field(
        default="connect", description="Spark Connect (gRPC) or the Thrift Server (HiveServer2)."
    )
    host: str = Field(description="Spark Connect or Thrift Server host.")
    port: int | None = Field(default=None, description="Default: 15002 (connect), 10000 (thrift).")
    connect_url: str | None = secret_field(
        default=None,
        description="Full Spark Connect URL (sc://host:port/;token=...); overrides host, port, "
        "token and use_ssl. Secret, because the URL may carry the token.",
    )
    token: str | None = secret_field(default=None, description="Bearer token (Spark Connect).")
    use_ssl: bool = Field(default=False, description="TLS for Spark Connect.")
    username: str | None = Field(default=None, description="Thrift Server user.")
    password: str | None = secret_field(default=None, description="Thrift Server password.")
    thrift_auth: Literal["NONE", "NOSASL", "LDAP", "CUSTOM", "KERBEROS"] = "NONE"
    kerberos_service_name: str = "hive"
    database: str = Field(default="default", description="Database (schema), or catalog.database.")
    tables: list[str] | None = Field(default=None, description="Restrict to these tables.")
    queries: dict[str, str] = Field(
        default_factory=dict, description="Extra streams: stream name -> Spark SQL SELECT."
    )
    cursor_columns: dict[str, str] = Field(
        default_factory=dict, description="table or query stream -> column for incremental sync."
    )
    fetch_size: int = Field(default=1000, ge=1, le=100_000)
    session_config: dict[str, str] = sensitive_mapping_field(
        default_factory=dict,
        description="Spark / Hive session settings, e.g. {'spark.sql.session.timeZone': 'UTC'}.",
    )
    timeout_seconds: float = 120.0

    @model_validator(mode="after")
    def _rules(self) -> SparkConfig:
        if self.thrift_auth in ("LDAP", "CUSTOM") and not self.username:
            raise ValueError(f"thrift_auth={self.thrift_auth} requires username and password")
        clash = set(self.queries) & set(self.tables or [])
        if clash:
            raise ValueError(f"query stream names clash with tables: {sorted(clash)}")
        return self


def build_connect_url(config: SparkConfig) -> str:
    if config.connect_url:
        return config.connect_url
    params = []
    if config.use_ssl:
        params.append("use_ssl=true")
    if config.token:
        params.append(f"token={config.token}")
    url = f"sc://{config.host}:{config.port or 15002}/"
    return url + ";" + ";".join(params) if params else url


# ---------------------------------------------------------------------------
# engines: what a transport has to provide (all blocking)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SparkTable:
    name: str
    columns: list[tuple[str, str]] = field(default_factory=list)
    """``(column name, Spark type)`` pairs in table order."""


class SparkEngine(Protocol):
    def list_tables(self, database: str, only: Collection[str] | None = None) -> list[SparkTable]:
        """The tables of ``database`` with their columns; ``only`` names the wanted ones, so
        the others are not described (a round trip each)."""
        ...

    def describe_query(self, sql: str) -> list[tuple[str, str]]: ...

    def execute(self, sql: str) -> Iterator[dict[str, Any]]:
        """Lazily yield rows as dicts; the iterator is consumed in fetch_size chunks."""
        ...

    def close(self) -> None: ...


EngineFactory = Callable[[SparkConfig], SparkEngine]


class SparkConnectEngine:
    def __init__(self, config: SparkConfig, session: Any | None = None) -> None:
        self._config = config
        self._spark = session
        self._owns_session = session is None

    def _session(self) -> Any:
        if self._spark is None:
            sql = require_extra("pyspark.sql", extra="spark", feature="spark connect")
            builder = sql.SparkSession.builder.remote(build_connect_url(self._config))
            for key, value in self._config.session_config.items():
                builder = builder.config(key, value)
            self._spark = builder.getOrCreate()
        return self._spark

    def list_tables(self, database: str, only: Collection[str] | None = None) -> list[SparkTable]:
        spark = self._session()
        tables: list[SparkTable] = []
        for table in spark.catalog.listTables(database):
            if getattr(table, "isTemporary", False):
                continue
            if only is not None and table.name not in only:
                continue
            columns = [
                (col.name, str(col.dataType))
                for col in spark.catalog.listColumns(table.name, database)
            ]
            tables.append(SparkTable(name=table.name, columns=columns))
        return tables

    def describe_query(self, sql: str) -> list[tuple[str, str]]:
        schema = self._session().sql(sql).schema
        return [(f.name, f.dataType.simpleString()) for f in schema.fields]

    def execute(self, sql: str) -> Iterator[dict[str, Any]]:
        frame = self._session().sql(sql)
        for row in frame.toLocalIterator():
            yield row.asDict(recursive=True)

    def close(self) -> None:
        if self._spark is not None and self._owns_session:
            spark, self._spark = self._spark, None
            spark.stop()


class ThriftEngine:
    """Spark Thrift Server through pyhive. ``use_ssl`` is not applied here: pyhive's
    binary transport has no TLS switch; put the server behind a TLS proxy instead."""

    def __init__(self, config: SparkConfig, connection: Any | None = None) -> None:
        self._config = config
        self._conn = connection
        self._owns_connection = connection is None

    def _connection(self) -> Any:
        if self._conn is None:
            hive = require_extra("pyhive.hive", extra="spark-thrift", feature="spark thrift")
            c = self._config
            self._conn = hive.connect(
                host=c.host,
                port=c.port or 10000,
                username=c.username,
                password=c.password,
                database=c.database.split(".")[-1],
                auth=c.thrift_auth,
                kerberos_service_name=c.kerberos_service_name,
                configuration=c.session_config or None,
            )
        return self._conn

    def _fetch_all(self, sql: str) -> list[tuple[Any, ...]]:
        cur = self._connection().cursor()
        try:
            cur.execute(sql)
            return list(cur.fetchall())
        finally:
            cur.close()

    def list_tables(self, database: str, only: Collection[str] | None = None) -> list[SparkTable]:
        tables: list[SparkTable] = []
        for row in self._fetch_all(f"SHOW TABLES IN {_qualified(database)}"):
            # (database, tableName, isTemporary) - the temporary flag is absent on old servers
            if len(row) > 2 and row[2]:
                continue
            name = str(row[1])
            if only is not None and name not in only:
                continue
            columns = parse_describe(
                self._fetch_all(f"DESCRIBE {_qualified(database)}.{_ident(name)}")
            )
            tables.append(SparkTable(name=name, columns=columns))
        return tables

    def describe_query(self, sql: str) -> list[tuple[str, str]]:
        return parse_describe(self._fetch_all(f"DESCRIBE QUERY {sql}"))

    def execute(self, sql: str) -> Iterator[dict[str, Any]]:
        cur = self._connection().cursor()
        cur.execute(sql)
        names = [str(d[0]).split(".")[-1] for d in cur.description or []]
        try:
            while True:
                batch = cur.fetchmany(self._config.fetch_size)
                if not batch:
                    return
                for row in batch:
                    yield dict(zip(names, row, strict=False))
        finally:
            cur.close()

    def close(self) -> None:
        if self._conn is not None and self._owns_connection:
            conn, self._conn = self._conn, None
            conn.close()


def parse_describe(rows: list[tuple[Any, ...]]) -> list[tuple[str, str]]:
    """Columns from ``DESCRIBE`` output; stops at the ``# Partition Information`` section."""
    columns: list[tuple[str, str]] = []
    for row in rows:
        name = str(row[0] or "").strip()
        if not name or name.startswith("#"):
            break
        columns.append((name, str(row[1] or "").strip()))
    return columns


def _default_engine(config: SparkConfig) -> SparkEngine:
    return ThriftEngine(config) if config.transport == "thrift" else SparkConnectEngine(config)


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------


class SparkSource(BaseSource[SparkConfig]):
    definition = ConnectorDefinition(
        name="spark",
        display_name="Apache Spark",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.WAREHOUSE,
        documentation_url="https://spark.apache.org/docs/latest/spark-connect-overview.html",
        icon="spark.svg",
        tags=frozenset({"warehouse", "lakehouse", "sql", "self-hosted"}),
    )
    Config = SparkConfig

    def __init__(self, config: SparkConfig, engine_factory: EngineFactory | None = None) -> None:
        super().__init__(config)
        self._factory = engine_factory or _default_engine
        self._engine: SparkEngine | None = None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def _get_engine(self) -> SparkEngine:
        if self._engine is None:
            self._engine = await asyncio.to_thread(self._factory, self.config)
        return self._engine

    async def close(self) -> None:
        if self._engine is not None:
            engine, self._engine = self._engine, None
            await asyncio.to_thread(engine.close)

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            engine = await self._get_engine()
            rows = await asyncio.to_thread(lambda: list(engine.execute("SELECT 1 AS ok")))
            if not rows:
                return CheckResult(ok=False, message="SELECT 1 returned no row")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        engine = await self._get_engine()
        database = self.config.database
        wanted = set(self.config.tables or []) or None
        streams: list[Stream] = []
        for table in await asyncio.to_thread(engine.list_tables, database, wanted):
            if wanted is not None and table.name not in wanted:
                continue
            streams.append(self._stream(table.name, table.columns, database))
        for name, sql in self.config.queries.items():
            columns = await asyncio.to_thread(engine.describe_query, sql)
            streams.append(self._stream(name, columns, database))
        return Catalog(streams=streams)

    def _stream(self, name: str, columns: list[tuple[str, str]], database: str) -> Stream:
        return table_stream(
            name,
            {c: _json_type(t) for c, t in columns},
            namespace=database,
            cursor=self.config.cursor_columns.get(name),
        )

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        engine = await self._get_engine()
        for configured in catalog.streams:
            stream = configured.stream
            cursor = incremental_cursor(configured)
            tracker = CursorTracker(
                stream.name,
                state,
                enabled=cursor is not None,
                ordered=True,
                checkpoint_every=CHECKPOINT_ROWS,
            )
            spark_type = str(
                (stream.json_schema.get("properties") or {})
                .get(cursor or "", {})
                .get(SPARK_TYPE_KEY)
                or ""
            )
            sql = self._select(stream.name, stream.namespace, cursor, tracker.start, spark_type)

            rows = await asyncio.to_thread(engine.execute, sql)
            try:
                async for raw in iterate_in_thread(rows, self.config.fetch_size):
                    data = {str(k): _to_json(v) for k, v in raw.items()}
                    if cursor:
                        checkpoint = tracker.observe(
                            data.get(cursor), exact=is_exact_cursor(raw.get(cursor))
                        )
                        if checkpoint:
                            yield checkpoint
                    yield Record(stream=stream.name, data=data, namespace=stream.namespace)
            finally:
                close = getattr(rows, "close", None)
                if callable(close):
                    await asyncio.to_thread(close)
            if final := tracker.final_state():
                yield final

    def _select(
        self, name: str, database: str | None, cursor: str | None, last: Any, spark_type: str
    ) -> str:
        query = self.config.queries.get(name)
        source = (
            f"({query}) AS q"
            if query
            else f"{_qualified(database or self.config.database)}.{_ident(name)}"
        )
        sql = f"SELECT * FROM {source}"
        if cursor:
            if last is not None:
                sql += f" WHERE {_ident(cursor)} > {sql_literal(last, spark_type)}"
            sql += f" ORDER BY {_ident(cursor)} ASC"
        return sql


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _qualified(name: str) -> str:
    """``catalog.database`` -> ```catalog`.`database```."""
    return ".".join(_ident(part) for part in name.split("."))


def sql_literal(value: Any, spark_type: str = "") -> str:
    """Render a cursor value as a Spark SQL literal, typed by the column's Spark type."""
    kind = spark_type.lower()
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, dt.datetime):
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    if isinstance(value, dt.date):
        return f"DATE '{value.isoformat()}'"
    text = str(value)
    if kind.startswith("timestamp"):
        return f"TIMESTAMP '{_escape(text)}'"
    if kind.startswith("date"):
        return f"DATE '{_escape(text)}'"
    if kind.startswith(_INTEGER_PREFIXES + _NUMBER_PREFIXES):
        float(text)  # raises on anything that is not a number
        return text
    return f"'{_escape(text)}'"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "''")


def _json_type(spark_type: str) -> dict[str, Any]:
    kind = spark_type.lower()
    if kind.startswith(_INTEGER_PREFIXES):
        out: dict[str, Any] = {"type": "integer"}
    elif kind.startswith(_NUMBER_PREFIXES):
        out = {"type": "number"}
    elif kind.startswith("boolean"):
        out = {"type": "boolean"}
    elif kind.startswith("timestamp"):
        out = {"type": "string", "format": "date-time"}
    elif kind.startswith("date"):
        out = {"type": "string", "format": "date"}
    elif kind.startswith("array"):
        out = {"type": "array"}
    elif kind.startswith(("struct", "map")):
        out = {"type": "object"}
    else:
        out = {"type": "string"}
    out[SPARK_TYPE_KEY] = spark_type
    return out
