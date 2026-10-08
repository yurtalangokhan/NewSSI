"""ClickHouse source over the native HTTP interface (no driver dependency).

Every table in ``database`` becomes a stream. Rows are streamed as
``JSONEachRow`` and decoded line by line, so memory stays bounded. Incremental
sync uses ``cursor_columns`` with a ``WHERE col > ?`` predicate and an
``ORDER BY`` on the cursor, so the server decides what "greater" means for the
column's type and the last row read carries the new cursor.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ..base import secret_field, sensitive_mapping_field
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.rest_source import RestSource, basic_auth_header
from ..common.tabular import CHECKPOINT_ROWS, table_stream
from ..errors import SourceError
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

_CH_TO_JSON: list[tuple[str, str]] = [
    ("UInt", "integer"),
    ("Int", "integer"),
    ("Float", "number"),
    ("Decimal", "number"),
    ("Bool", "boolean"),
    ("Array", "array"),
    ("Map", "object"),
    ("Tuple", "object"),
    ("JSON", "object"),
]


class ClickHouseConfig(BaseModel):
    url: str = Field(default="http://localhost:8123", description="HTTP interface URL.")
    database: str = "default"
    username: str = "default"
    password: str = secret_field(default="")
    tables: list[str] | None = Field(default=None, description="Restrict to these tables.")
    cursor_columns: dict[str, str] = Field(
        default_factory=dict, description="table name -> column used for incremental sync."
    )
    max_block_size: int = Field(default=10_000, ge=100, le=1_000_000)
    settings: dict[str, str] = sensitive_mapping_field(
        default_factory=dict, description="Extra ClickHouse query settings sent as URL params."
    )
    timeout_seconds: float = 300.0
    verify_ssl: bool = True


class ClickHouseSource(RestSource[ClickHouseConfig]):
    definition = ConnectorDefinition(
        name="clickhouse",
        display_name="ClickHouse",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.WAREHOUSE,
        documentation_url="https://clickhouse.com/docs/interfaces/http",
        icon="clickhouse.svg",
        tags=frozenset({"database", "warehouse", "olap"}),
    )
    Config = ClickHouseConfig
    check_path: ClassVar[str] = "/ping"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    def base_url(self) -> str:
        return self.config.url

    def auth_headers(self) -> dict[str, str]:
        return basic_auth_header(self.config.username, self.config.password)

    # ---- query helpers ------------------------------------------------------------

    def _params(self) -> dict[str, Any]:
        return {
            "database": self.config.database,
            "default_format": "JSONEachRow",
            "max_block_size": self.config.max_block_size,
            # older servers default this to 1 and would quote UInt64/Int64 values
            "output_format_json_quote_64bit_integers": 0,
            **self.config.settings,
        }

    async def _query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        resp = await self.request(
            "POST", "/", params={**self._params(), **(params or {})}, content=sql.encode()
        )
        return [json.loads(line) for line in resp.text.splitlines() if line.strip()]

    async def _stream_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        hdrs = (
            dict(self.auth_headers()) if self._client is not None and not self._owns_client else {}
        )
        await self.prepare_request(hdrs)
        async with self._get_client().stream(
            "POST",
            "/",
            params={**self._params(), **(params or {})},
            content=sql.encode(),
            headers=hdrs,
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")
                raise SourceError(f"ClickHouse {resp.status_code}: {body[:300]}")
            async for line in resp.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    # ---- connector API --------------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await self._query("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        wanted = set(self.config.tables or [])
        rows = await self._query(
            "SELECT table, name, type, is_in_primary_key FROM system.columns "
            "WHERE database = {db:String} ORDER BY table, position",
            params={"param_db": self.config.database},
        )
        tables: dict[str, dict[str, Any]] = {}
        pks: dict[str, list[list[str]]] = {}
        for r in rows:
            tables.setdefault(r["table"], {})[r["name"]] = {"type": _json_type(r["type"])}
            if int(r.get("is_in_primary_key") or 0):
                pks.setdefault(r["table"], []).append([r["name"]])
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

            sql = f"SELECT * FROM {_ident(self.config.database)}.{_ident(stream.name)}"
            params: dict[str, Any] = {}
            if cursor:
                if tracker.start is not None:
                    sql += f" WHERE {_ident(cursor)} > {{last:String}}"
                    params["param_last"] = str(tracker.start)
                sql += f" ORDER BY {_ident(cursor)} ASC"

            async for row in self._stream_query(sql, params):
                if cursor:
                    # Rows arrive in the server's order; nothing is compared here.
                    checkpoint = tracker.observe(row.get(cursor))
                    if checkpoint:
                        yield checkpoint
                yield Record(stream=stream.name, data=row, namespace=self.config.database)
            if final := tracker.final_state():
                yield final


def _ident(name: str) -> str:
    """Backtick-quoted identifier; ClickHouse escapes inside it with a backslash."""
    return "`" + name.replace("\\", "\\\\").replace("`", "\\`") + "`"


def _json_type(ch_type: str) -> str:
    base = ch_type
    for wrapper in ("Nullable(", "LowCardinality("):
        if base.startswith(wrapper):
            base = base[len(wrapper) : -1]
    for prefix, json_type in _CH_TO_JSON:
        if base.startswith(prefix):
            return json_type
    return "string"
