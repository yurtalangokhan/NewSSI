"""MySQL / MariaDB source (requires the ``mysql`` extra: aiomysql).

Every table in the configured database becomes a stream. Incremental sync is
supported on any column named in ``cursor_columns``. Rows are streamed with an
unbuffered server-side cursor so memory stays bounded.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSource, secret_field
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.tabular import (
    CHECKPOINT_ROWS,
    backtick_ident,
    is_exact_cursor,
    table_stream,
    to_json_value,
)
from ..extras import optional_module, require_extra
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


def _ident(name: str) -> str:
    """A quoted name inside a statement that aiomysql formats.

    The driver builds what it sends as ``sql % escaped_args``, also when there
    are no arguments, so a ``%`` that belongs to a name is written twice.
    """
    return backtick_ident(name).replace("%", "%%")


_MYSQL_TO_JSON: dict[str, str] = {
    "int": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "tinyint": "integer",
    "mediumint": "integer",
    "decimal": "number",
    "float": "number",
    "double": "number",
    "json": "object",
    "bit": "integer",
}


class MySqlConfig(BaseModel):
    host: str
    port: int = 3306
    database: str
    username: str
    password: str = secret_field(default="")
    tables: list[str] | None = Field(default=None, description="Restrict to these tables.")
    cursor_columns: dict[str, str] = Field(
        default_factory=dict, description="table name -> column used for incremental sync."
    )
    fetch_size: int = Field(default=500, ge=1, le=10_000)
    ssl: bool = False
    connect_timeout_seconds: float = 10.0


class MySqlSource(BaseSource[MySqlConfig]):
    definition = ConnectorDefinition(
        name="mysql",
        display_name="MySQL",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.DATABASE,
        documentation_url="https://dev.mysql.com/doc/",
        icon="mysql.svg",
        tags=frozenset({"database", "sql"}),
    )
    Config = MySqlConfig

    def __init__(self, config: MySqlConfig, pool: Any | None = None) -> None:
        super().__init__(config)
        self._pool = pool
        self._owns_pool = pool is None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- connection -------------------------------------------------------

    async def _get_pool(self) -> Any:
        if self._pool is None:
            aiomysql = require_extra("aiomysql", extra="mysql", feature="mysql source")
            c = self.config
            self._pool = await aiomysql.create_pool(
                host=c.host,
                port=c.port,
                db=c.database,
                user=c.username,
                password=c.password,
                ssl=c.ssl or None,
                connect_timeout=c.connect_timeout_seconds,
                minsize=1,
                maxsize=4,
                autocommit=True,
                conv=_decoders(),
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None and self._owns_pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def _fetch_all(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.cursor(_dict_cursor()) as cur:
            await cur.execute(sql, args)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await self._fetch_all("SELECT 1 AS ok")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        wanted = set(self.config.tables or [])
        columns = await self._fetch_all(
            """
            SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name, DATA_TYPE AS data_type,
                   COLUMN_KEY AS column_key
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (self.config.database,),
        )
        tables: dict[str, dict[str, Any]] = {}
        pks: dict[str, list[list[str]]] = {}
        for c in columns:
            t = c["table_name"]
            tables.setdefault(t, {})[c["column_name"]] = {
                "type": _MYSQL_TO_JSON.get(str(c["data_type"]).lower(), "string")
            }
            if c.get("column_key") == "PRI":
                pks.setdefault(t, []).append([c["column_name"]])

        streams: list[Stream] = []
        for table, props in tables.items():
            if wanted and table not in wanted:
                continue
            cursor = self.config.cursor_columns.get(table)
            streams.append(
                table_stream(
                    table,
                    props,
                    namespace=self.config.database,
                    cursor=cursor,
                    primary_key=pks.get(table),
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        pool = await self._get_pool()
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

            sql = f"SELECT * FROM {_ident(stream.name)}"
            args: tuple[Any, ...] = ()
            if cursor:
                if tracker.start is not None:
                    # MySQL compares a temporal column with the ISO text it is given.
                    sql += f" WHERE {_ident(cursor)} > %s"
                    args = (tracker.start,)
                sql += f" ORDER BY {_ident(cursor)} ASC"

            async with pool.acquire() as conn:
                cursor_cm = conn.cursor(_ss_dict_cursor())
                cur = await cursor_cm.__aenter__()
                exhausted = False
                try:
                    await cur.execute(sql, args)
                    while True:
                        rows = await cur.fetchmany(self.config.fetch_size)
                        if not rows:
                            break
                        for row in rows:
                            raw = dict(row)
                            data = {k: to_json_value(v) for k, v in raw.items()}
                            if cursor:
                                checkpoint = tracker.observe(
                                    data.get(cursor), exact=is_exact_cursor(raw.get(cursor))
                                )
                                if checkpoint:
                                    yield checkpoint
                            yield Record(stream=stream.name, data=data, namespace=stream.namespace)
                    exhausted = True
                finally:
                    if exhausted:
                        await cursor_cm.__aexit__(None, None, None)
                    else:
                        # Stopped early (a preview, a cancellation): closing the streaming
                        # cursor would read the rest of the table off the socket first. The
                        # pool drops a closed connection on release.
                        conn.close()
            if final := tracker.final_state():
                yield final


def _dict_cursor() -> Any:
    return _aiomysql_attr("DictCursor")


def _ss_dict_cursor() -> Any:
    return _aiomysql_attr("SSDictCursor")


def _aiomysql_attr(name: str) -> Any:
    """Cursor class from aiomysql, or ``None`` when an injected pool is used without it."""
    aiomysql = optional_module("aiomysql")
    return getattr(aiomysql, name) if aiomysql is not None else None


def _decoders() -> dict[int, Any]:
    """pymysql's decoders plus the two column kinds it hands over raw.

    A JSON column arrives as its text (pymysql decodes it with the connection
    charset, so the decoder sees ``str``) against the declared ``object``; a
    BIT(n) column arrives as the raw bytes of the bit field. Seen live against
    MySQL 8.4.
    """
    converters = require_extra("pymysql.converters", extra="mysql", feature="mysql source")
    constants = require_extra("pymysql.constants", extra="mysql", feature="mysql source")
    field_type = constants.FIELD_TYPE
    return {
        **converters.decoders,
        field_type.JSON: json.loads,
        field_type.BIT: lambda raw: int.from_bytes(raw, "big"),
    }
