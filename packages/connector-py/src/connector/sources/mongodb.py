"""MongoDB source (requires the ``mongodb`` extra: pymongo >= 4.9 with its async client).

Every collection in the configured database becomes a stream. Incremental sync
uses ``cursor_fields`` (``{"orders": "updatedAt"}``) with a ``$gt`` filter;
``_id`` works too because ObjectIds are monotonic per process. Documents are
streamed through a server cursor with ``batch_size``, so memory stays bounded.
BSON scalars are converted to JSON-safe values (``ObjectId`` -> str,
``datetime`` -> ISO 8601, ``Decimal128`` -> float, ``bytes`` -> hex).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSource, secret_field
from ..common.cursor import CursorTracker, incremental_cursor
from ..common.declarative import dig
from ..common.json_schema import add_properties
from ..common.tabular import CHECKPOINT_ROWS, is_exact_cursor, table_stream, to_json_value
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


class MongoDbConfig(BaseModel):
    connection_string: str = secret_field(
        description="mongodb:// or mongodb+srv:// URI (credentials included, hence secret)."
    )
    database: str
    collections: list[str] | None = Field(
        default=None, description="Restrict to these collections."
    )
    cursor_fields: dict[str, str] = Field(
        default_factory=dict, description="collection -> field used for incremental sync."
    )
    batch_size: int = Field(default=500, ge=1, le=10_000)
    schema_sample_size: int = Field(default=100, ge=1, le=10_000)
    connect_timeout_seconds: float = 10.0
    exclude_system_collections: bool = True


class MongoDbSource(BaseSource[MongoDbConfig]):
    definition = ConnectorDefinition(
        name="mongodb",
        display_name="MongoDB",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.DATABASE,
        documentation_url="https://www.mongodb.com/docs/",
        icon="mongodb.svg",
        tags=frozenset({"database", "nosql"}),
    )
    Config = MongoDbConfig

    def __init__(self, config: MongoDbConfig, client: Any | None = None) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- connection -------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            pymongo = require_extra("pymongo", extra="mongodb", feature="mongodb source")
            timeout_ms = int(self.config.connect_timeout_seconds * 1000)
            self._client = pymongo.AsyncMongoClient(
                self.config.connection_string,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
            )
        return self._client

    def _db(self) -> Any:
        return self._get_client()[self.config.database]

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None

    # ---- connector API ------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await self._db().command("ping")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        db = self._db()
        names: list[str] = sorted(await db.list_collection_names())
        wanted = set(self.config.collections or [])
        streams: list[Stream] = []
        for name in names:
            if self.config.exclude_system_collections and name.startswith("system."):
                continue
            if wanted and name not in wanted:
                continue
            props: dict[str, Any] = {}
            async for doc in db[name].find({}, limit=self.config.schema_sample_size):
                # the values ``read`` delivers: Decimal128 -> number, ObjectId/datetime -> string
                add_properties(props, {k: _to_json_scalar(v) for k, v in doc.items()})
            streams.append(
                table_stream(
                    name,
                    props,
                    namespace=self.config.database,
                    cursor=self.config.cursor_fields.get(name),
                    primary_key=[["_id"]],
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        db = self._db()
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

            query: dict[str, Any] = {}
            if cursor and tracker.start is not None:
                query[cursor] = {"$gt": _from_json_scalar(tracker.start, cursor)}
            find = db[stream.name].find(query, batch_size=self.config.batch_size)
            if cursor:
                find = find.sort(cursor, 1)

            async for doc in find:
                data = {k: _to_json_scalar(v) for k, v in doc.items()}
                if cursor:
                    # Strings sort by the collection's collation, which may call two
                    # different ones equal: never a mid-stream checkpoint boundary.
                    checkpoint = tracker.observe(
                        dig(data, cursor), exact=is_exact_cursor(dig(doc, cursor))
                    )
                    if checkpoint:
                        yield checkpoint
                yield Record(stream=stream.name, data=data, namespace=stream.namespace)
            if final := tracker.final_state():
                yield final


# ---------------------------------------------------------------------------
# BSON <-> JSON helpers (pure python so tests run without pymongo)
# ---------------------------------------------------------------------------


def _to_json_scalar(value: Any) -> Any:
    return to_json_value(value, _bson_to_json)


def _bson_to_json(value: Any) -> Any:
    if type(value).__name__ == "Decimal128":
        return float(value.to_decimal())
    # ObjectId, Timestamp, Regex, ... -> string representation
    return str(value)


def _from_json_scalar(value: Any, field: str) -> Any:
    """Best effort reverse conversion for cursor comparison."""
    if field == "_id" and isinstance(value, str):
        bson = optional_module("bson")
        try:
            return bson.ObjectId(value) if bson is not None else value
        except Exception:  # noqa: BLE001 - not an ObjectId: fall back to string compare
            return value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return value
    return value
