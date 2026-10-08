"""Microsoft SQL Server source: base tables of one database, read with pyodbc.

Requires the ``mssql`` extra (pyodbc) and an ODBC driver on the host;
``ODBC Driver 18 for SQL Server`` is assumed unless ``odbc_driver`` says
otherwise. Azure SQL Database works the same way.

Every base table in the configured ``schemas`` becomes a stream. Incremental
sync uses ``cursor_columns`` (``{"Orders": "ModifiedAt"}`` or
``{"sales.Orders": ...}``) with a ``WHERE [col] > ?`` predicate. Rows are pulled
from a forward-only cursor in ``fetch_size`` chunks, so memory stays bounded.
pyodbc is blocking, so every database call runs in a worker thread.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSource, secret_field, sensitive_mapping_field
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.tabular import (
    CHECKPOINT_ROWS,
    from_json_scalar,
    is_exact_cursor,
    table_stream,
    to_json_value,
)
from ..common.tabular import bracket_ident as _ident
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

_MSSQL_TO_JSON: dict[str, str] = {
    "int": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "tinyint": "integer",
    "decimal": "number",
    "numeric": "number",
    "money": "number",
    "smallmoney": "number",
    "float": "number",
    "real": "number",
    "bit": "boolean",
}

ConnectFactory = Callable[["MssqlConfig"], Any]


class MssqlConfig(BaseModel):
    host: str
    port: int = 1433
    database: str
    username: str | None = Field(
        default=None, description="SQL login. Leave empty for Windows integrated authentication."
    )
    password: str = secret_field(default="")
    odbc_driver: str = Field(
        default="ODBC Driver 18 for SQL Server", description="Name of the installed ODBC driver."
    )
    encrypt: bool = True
    trust_server_certificate: bool = Field(
        default=False,
        description=(
            "Accept a self-signed server certificate: needed with the default encrypt=True "
            "against a server, such as a local container, whose certificate no CA signed."
        ),
    )
    schemas: list[str] = Field(default_factory=lambda: ["dbo"])
    tables: list[str] | None = Field(
        default=None, description="Restrict to these tables (schema.table or table)."
    )
    cursor_columns: dict[str, str] = Field(
        default_factory=dict, description="table name -> column used for incremental sync."
    )
    fetch_size: int = Field(default=500, ge=1, le=10_000)
    connect_timeout_seconds: float = 10.0
    extra_connection_params: dict[str, str] = sensitive_mapping_field(
        default_factory=dict,
        description="Additional ODBC keywords, e.g. {'ApplicationIntent': 'ReadOnly'}.",
    )


def build_connection_string(config: MssqlConfig) -> str:
    """ODBC connection string; values with ``;`` or braces are brace-quoted."""
    parts: dict[str, str] = {
        "DRIVER": "{" + config.odbc_driver + "}",
        "SERVER": f"{config.host},{config.port}",
        "DATABASE": _odbc_value(config.database),
        "Encrypt": "yes" if config.encrypt else "no",
        "TrustServerCertificate": "yes" if config.trust_server_certificate else "no",
        "Connection Timeout": str(int(config.connect_timeout_seconds)),
    }
    if config.username:
        parts["UID"] = _odbc_value(config.username)
        parts["PWD"] = _odbc_value(config.password)
    else:
        parts["Trusted_Connection"] = "yes"
    parts.update({k: _odbc_value(v) for k, v in config.extra_connection_params.items()})
    return ";".join(f"{k}={v}" for k, v in parts.items()) + ";"


def _odbc_value(value: str) -> str:
    if any(ch in value for ch in ";{}") or value != value.strip():
        return "{" + value.replace("}", "}}") + "}"
    return value


def _default_connect(config: MssqlConfig) -> Any:
    pyodbc = require_extra(
        "pyodbc", extra="mssql", feature="mssql source (plus an ODBC driver on the host)"
    )
    return pyodbc.connect(
        build_connection_string(config), timeout=int(config.connect_timeout_seconds)
    )


class MssqlSource(BaseSource[MssqlConfig]):
    definition = ConnectorDefinition(
        name="mssql",
        display_name="Microsoft SQL Server",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.DATABASE,
        documentation_url="https://learn.microsoft.com/sql/connect/python/pyodbc/python-sql-driver-pyodbc",
        icon="mssql.svg",
        tags=frozenset({"database", "sql", "microsoft"}),
    )
    Config = MssqlConfig

    def __init__(self, config: MssqlConfig, connect: ConnectFactory | None = None) -> None:
        super().__init__(config)
        self._connect = connect or _default_connect
        self._conn: Any | None = None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- connection -------------------------------------------------------

    async def _connection(self) -> Any:
        if self._conn is None:
            self._conn = await asyncio.to_thread(self._connect, self.config)
        return self._conn

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            await asyncio.to_thread(conn.close)

    async def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = await self._connection()

        def _run() -> list[dict[str, Any]]:
            cur = _open_cursor(conn, sql, params)
            try:
                names = [d[0] for d in cur.description]
                return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]
            finally:
                cur.close()

        return await asyncio.to_thread(_run)

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await self._fetch_all("SELECT 1 AS ok")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        schemas = tuple(self.config.schemas)
        placeholders = ", ".join("?" for _ in schemas)
        columns = await self._fetch_all(
            f"""
            SELECT c.TABLE_SCHEMA AS table_schema, c.TABLE_NAME AS table_name,
                   c.COLUMN_NAME AS column_name, c.DATA_TYPE AS data_type
            FROM INFORMATION_SCHEMA.COLUMNS c
            JOIN INFORMATION_SCHEMA.TABLES t
              ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE' AND c.TABLE_SCHEMA IN ({placeholders})
            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
            """,
            schemas,
        )
        keys = await self._fetch_all(
            f"""
            SELECT kcu.TABLE_SCHEMA AS table_schema, kcu.TABLE_NAME AS table_name,
                   kcu.COLUMN_NAME AS column_name
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA AND tc.TABLE_NAME = kcu.TABLE_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_SCHEMA IN ({placeholders})
            ORDER BY kcu.ORDINAL_POSITION
            """,
            schemas,
        )
        pk_map: dict[tuple[str, str], list[list[str]]] = {}
        for k in keys:
            pk_map.setdefault((k["table_schema"], k["table_name"]), []).append([k["column_name"]])

        tables: dict[tuple[str, str], dict[str, Any]] = {}
        for c in columns:
            key = (c["table_schema"], c["table_name"])
            tables.setdefault(key, {})[c["column_name"]] = {
                "type": _MSSQL_TO_JSON.get(str(c["data_type"]).lower(), "string")
            }

        wanted = set(self.config.tables or [])
        streams: list[Stream] = []
        for (schema, table), props in tables.items():
            if wanted and table not in wanted and f"{schema}.{table}" not in wanted:
                continue
            cursor = self.config.cursor_columns.get(f"{schema}.{table}") or (
                self.config.cursor_columns.get(table)
            )
            streams.append(
                table_stream(
                    table if schema.lower() == "dbo" else f"{schema}.{table}",
                    props,
                    namespace=schema,
                    cursor=cursor,
                    primary_key=pk_map.get((schema, table)),
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        conn = await self._connection()
        for configured in catalog.streams:
            stream = configured.stream
            schema = stream.namespace or "dbo"
            table = stream.name.split(".", 1)[-1]
            cursor = incremental_cursor(configured)
            tracker = CursorTracker(
                stream.name,
                state,
                enabled=cursor is not None,
                ordered=True,
                checkpoint_every=CHECKPOINT_ROWS,
            )

            sql = f"SELECT * FROM {_ident(schema)}.{_ident(table)}"
            params: tuple[Any, ...] = ()
            if cursor:
                if tracker.start is not None:
                    sql += f" WHERE {_ident(cursor)} > ?"
                    params = (from_json_scalar(tracker.start),)
                sql += f" ORDER BY {_ident(cursor)} ASC"

            cur = await asyncio.to_thread(_open_cursor, conn, sql, params)
            try:
                names = [d[0] for d in cur.description]
                while True:
                    rows = await asyncio.to_thread(cur.fetchmany, self.config.fetch_size)
                    if not rows:
                        break
                    for row in rows:
                        raw = dict(zip(names, row, strict=False))
                        data = {k: to_json_value(v) for k, v in raw.items()}
                        if cursor:
                            checkpoint = tracker.observe(
                                data.get(cursor), exact=is_exact_cursor(raw.get(cursor))
                            )
                            if checkpoint:
                                yield checkpoint
                        yield Record(stream=stream.name, data=data, namespace=schema)
            finally:
                await asyncio.to_thread(cur.close)
            if final := tracker.final_state():
                yield final


def _open_cursor(conn: Any, sql: str, params: tuple[Any, ...]) -> Any:
    cur = conn.cursor()
    try:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
    except Exception:
        cur.close()
        raise
    return cur
