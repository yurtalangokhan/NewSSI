"""PostgreSQL source (requires the ``postgres`` extra: asyncpg).

Every table in the configured schemas becomes a stream. Incremental sync is
supported on any column named in ``cursor_columns`` (``{"orders": "updated_at"}``)
using a simple ``WHERE cursor > $last`` predicate. Rows are streamed through a
server-side cursor, so memory stays bounded regardless of table size.
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
    ansi_ident,
    from_json_scalar,
    is_exact_cursor,
    table_stream,
    to_json_value,
)
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

_PG_TO_JSON: dict[str, str] = {
    "integer": "integer",
    "bigint": "integer",
    "smallint": "integer",
    "numeric": "number",
    "real": "number",
    "double precision": "number",
    "boolean": "boolean",
    "json": "object",
    "jsonb": "object",
    "ARRAY": "array",
}


class PostgresConfig(BaseModel):
    host: str
    port: int = 5432
    database: str
    username: str
    password: str = secret_field(default="")
    schemas: list[str] = Field(default_factory=lambda: ["public"])
    tables: list[str] | None = Field(
        default=None, description="Restrict to these tables (schema.table or table)."
    )
    cursor_columns: dict[str, str] = Field(
        default_factory=dict,
        description="table name -> column used for incremental sync.",
    )
    fetch_size: int = Field(default=500, ge=1, le=10_000)
    ssl: bool = False
    connect_timeout_seconds: float = 10.0


async def _decode_json_columns(connection: Any) -> None:
    """Register ``json`` / ``jsonb`` codecs on a pool connection.

    asyncpg hands those columns over as text; discovery declares them as
    ``object``, so the records carry the decoded value instead.
    """
    for typename in ("json", "jsonb"):
        await connection.set_type_codec(
            typename, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


class PostgresSource(BaseSource[PostgresConfig]):
    definition = ConnectorDefinition(
        name="postgres",
        icon="postgres.svg",
        display_name="PostgreSQL",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.DATABASE,
        documentation_url="https://www.postgresql.org/docs/",
        tags=frozenset({"database", "sql"}),
    )
    Config = PostgresConfig

    def __init__(self, config: PostgresConfig, pool: Any | None = None) -> None:
        super().__init__(config)
        self._pool = pool
        self._owns_pool = pool is None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- connection -------------------------------------------------------

    async def _get_pool(self) -> Any:
        if self._pool is None:
            asyncpg = require_extra("asyncpg", extra="postgres", feature="postgres source")
            c = self.config
            self._pool = await asyncpg.create_pool(
                host=c.host,
                port=c.port,
                database=c.database,
                user=c.username,
                password=c.password,
                ssl=c.ssl or None,
                timeout=c.connect_timeout_seconds,
                min_size=1,
                max_size=4,
                init=_decode_json_columns,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None and self._owns_pool:
            await self._pool.close()
            self._pool = None

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        pool = await self._get_pool()
        wanted = set(self.config.tables or [])
        streams: list[Stream] = []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ANY($1::text[])
                ORDER BY table_schema, table_name, ordinal_position
                """,
                self.config.schemas,
            )
            pks = await conn.fetch(
                """
                SELECT tc.table_schema, tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = ANY($1::text[])
                """,
                self.config.schemas,
            )
        pk_map: dict[tuple[str, str], list[list[str]]] = {}
        for r in pks:
            pk_map.setdefault((r["table_schema"], r["table_name"]), []).append([r["column_name"]])

        tables: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rows:
            key = (r["table_schema"], r["table_name"])
            tables.setdefault(key, {})[r["column_name"]] = {
                "type": _PG_TO_JSON.get(r["data_type"], "string")
            }

        for (schema, table), props in tables.items():
            if wanted and table not in wanted and f"{schema}.{table}" not in wanted:
                continue
            cursor = self.config.cursor_columns.get(table) or self.config.cursor_columns.get(
                f"{schema}.{table}"
            )
            streams.append(
                table_stream(
                    table if schema == "public" else f"{schema}.{table}",
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
        pool = await self._get_pool()
        for configured in catalog.streams:
            stream = configured.stream
            schema = stream.namespace or "public"
            table = stream.name.split(".", 1)[-1]
            cursor = incremental_cursor(configured)
            tracker = CursorTracker(
                stream.name,
                state,
                enabled=cursor is not None,
                ordered=True,
                checkpoint_every=CHECKPOINT_ROWS,
            )

            sql = f"SELECT * FROM {ansi_ident(schema)}.{ansi_ident(table)}"
            args: list[Any] = []
            if cursor:
                if tracker.start is not None:
                    sql += f" WHERE {ansi_ident(cursor)} > $1"
                    args.append(from_json_scalar(tracker.start))
                sql += f" ORDER BY {ansi_ident(cursor)} ASC"

            async with pool.acquire() as conn, conn.transaction():
                async for row in conn.cursor(sql, *args, prefetch=self.config.fetch_size):
                    raw = dict(row)
                    data = {k: to_json_value(v) for k, v in raw.items()}
                    if cursor:
                        checkpoint = tracker.observe(
                            data.get(cursor), exact=is_exact_cursor(raw.get(cursor))
                        )
                        if checkpoint:
                            yield checkpoint
                    yield Record(stream=stream.name, data=data, namespace=schema)
            if final := tracker.final_state():
                yield final
