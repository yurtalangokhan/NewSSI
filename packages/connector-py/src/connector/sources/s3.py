"""Amazon S3 (and S3-compatible, e.g. MinIO) file source (requires the ``s3`` extra: boto3).

A stream is a named glob over object keys plus a file format (``csv``, ``jsonl``
or ``json``). Objects are listed with pagination, read one at a time and parsed
line by line, so memory is bounded by one row (csv/jsonl) or one file (json).
Incremental sync uses the object's ``LastModified`` timestamp as the cursor.

Every record carries ``_source_file`` and ``_source_file_last_modified`` so
downstream consumers can trace provenance.

boto3 is synchronous; calls are offloaded with ``asyncio.to_thread`` so the
event loop stays responsive.
"""

from __future__ import annotations

import asyncio
import io
import itertools
import posixpath
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, Field

from ..base import BaseSource
from ..common.blocking import iterate_in_thread
from ..common.cursor import CursorTracker, ReadAtCursor
from ..common.file_formats import (
    CHECKPOINT_FILES,
    EXT_TO_FORMAT,
    FileFormat,
    glob_match,
    parse_records,
)
from ..common.json_schema import add_properties
from ..common.s3_connection import AwsConnection, build_s3_client
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

S3ConfigT = TypeVar("S3ConfigT", bound="S3SourceOptions")

DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


class S3StreamConfig(BaseModel):
    name: str = Field(description="Stream name.")
    glob: str = Field(default="**", description="fnmatch pattern on the key relative to `prefix`.")
    format: FileFormat | None = Field(
        default=None, description="File format. Inferred from the extension when omitted."
    )
    csv_delimiter: str = Field(
        default=",",
        description="Column delimiter of csv files. A '.tsv' file is split on tabs unless "
        "this is changed.",
    )
    encoding: str = "utf-8"


class S3SourceOptions(BaseModel):
    """What to read; independent of how the object store is reached."""

    bucket: str
    prefix: str = Field(default="", description="Key prefix to scan (folder).")
    streams: list[S3StreamConfig] = Field(
        default_factory=lambda: [S3StreamConfig(name="files")],
        description="Named globs. Default: one stream over every supported file under `prefix`.",
    )
    schema_sample_rows: int = Field(default=50, ge=1, le=10_000)
    max_file_size_bytes: int | None = Field(
        default=DEFAULT_MAX_FILE_SIZE_BYTES,
        description="Skip objects larger than this, in bytes (default 50 MiB; null = no limit). "
        "A text or JSON object is parsed as a whole, so this bounds the memory of a sync.",
    )

    def client_kwargs(self) -> dict[str, Any]:
        """boto3 client arguments. Supplied by the connection model a config is combined with."""
        raise NotImplementedError


class S3Config(AwsConnection, S3SourceOptions):
    """Amazon S3 source configuration."""


class S3Source(BaseSource[S3ConfigT]):
    definition = ConnectorDefinition(
        name="s3",
        display_name="Amazon S3",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://docs.aws.amazon.com/s3/",
        icon="s3.svg",
        tags=frozenset({"file", "cloud", "storage"}),
    )
    Config: ClassVar[type[BaseModel]] = S3Config
    extra_name = "s3"

    def __init__(self, config: S3ConfigT, client: Any | None = None) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- client -------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = build_s3_client(self.config.client_kwargs(), extra_name=self.extra_name)
        return self._client

    async def close(self) -> None:
        """Close the client this source built (its connection pool); an injected one stays."""
        if self._client is not None and self._owns_client:
            close = getattr(self._client, "close", None)
            if close is not None:
                await asyncio.to_thread(close)
            self._client = None

    async def _list_objects(self) -> list[dict[str, Any]]:
        """All objects under ``prefix`` as ``{key, rel_key, last_modified, size}``."""

        def _sync() -> list[dict[str, Any]]:
            client = self._get_client()
            paginator = client.get_paginator("list_objects_v2")
            out: list[dict[str, Any]] = []
            for page in paginator.paginate(Bucket=self.config.bucket, Prefix=self.config.prefix):
                for obj in page.get("Contents", []) or []:
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    out.append(
                        {
                            "key": key,
                            "rel_key": key[len(self.config.prefix) :].lstrip("/"),
                            "last_modified": _as_utc(obj["LastModified"]),
                            "size": int(obj.get("Size", 0)),
                        }
                    )
            return out

        return await asyncio.to_thread(_sync)

    async def _open(self, key: str) -> io.BufferedReader:
        def _sync() -> io.BufferedReader:
            body = self._get_client().get_object(Bucket=self.config.bucket, Key=key)["Body"]
            return io.BufferedReader(_RawBody(body))

        return await asyncio.to_thread(_sync)

    # ---- connector API --------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await asyncio.to_thread(
                lambda: self._get_client().head_bucket(Bucket=self.config.bucket)
            )
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        objects = await self._list_objects()
        streams: list[Stream] = []
        for sc in self.config.streams:
            matched = self._match(objects, sc)
            props: dict[str, Any] = {}
            if matched and self._format_for(sc, matched[0]["key"]) == "text":
                props["content"] = {"type": "string"}  # one document per file; nothing to read
            elif matched:
                first = matched[0]
                reader = await self._open(first["key"])
                with reader:
                    sample = itertools.islice(
                        self._rows(reader, sc, first["key"]), self.config.schema_sample_rows
                    )
                    for row in await asyncio.to_thread(list, sample):
                        add_properties(props, row)
            props.setdefault("_source_file", {"type": "string"})
            props.setdefault("_source_file_last_modified", {"type": "string"})
            streams.append(
                Stream(
                    name=sc.name,
                    json_schema={"type": "object", "properties": props},
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["_source_file_last_modified"],
                )
            )
        return Catalog(streams=streams)

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        by_name = {sc.name: sc for sc in self.config.streams}
        objects = await self._list_objects()
        for configured in catalog.streams:
            sc = by_name.get(configured.stream.name)
            if sc is None:
                continue
            # Objects are read oldest first, so the position can be saved between them.
            tracker = CursorTracker(
                sc.name,
                state,
                enabled=configured.sync_mode is SyncMode.INCREMENTAL,
                ordered=True,
                checkpoint_every=CHECKPOINT_FILES,
            )
            read_at = ReadAtCursor(tracker, state.get(sc.name))

            for obj in self._match(objects, sc):
                if not read_at.due(obj["last_modified"], obj["key"]):
                    continue
                stamp = obj["last_modified"].isoformat()
                checkpoint = tracker.observe(stamp)
                if checkpoint:
                    yield read_at.attach(checkpoint)
                read_at.note(stamp, obj["key"])
                reader = await self._open(obj["key"])
                try:
                    # The body is a network stream that the parser reads as it goes.
                    async for row in iterate_in_thread(self._rows(reader, sc, obj["key"])):
                        row["_source_file"] = obj["key"]
                        row["_source_file_last_modified"] = stamp
                        yield Record(stream=sc.name, data=row)
                finally:
                    await asyncio.to_thread(reader.close)
            if final := tracker.final_state():
                yield read_at.attach(final)

    # ---- helpers ----------------------------------------------------------------

    def _match(self, objects: list[dict[str, Any]], sc: S3StreamConfig) -> list[dict[str, Any]]:
        """The objects of stream ``sc``, oldest first: glob, known format, within the size cap."""
        pattern = sc.glob
        cap = self.config.max_file_size_bytes
        hits = [
            o
            for o in objects
            if glob_match(o["rel_key"], pattern)
            and self._format_for(sc, o["key"]) is not None
            and (cap is None or o["size"] <= cap)
        ]
        return sorted(hits, key=lambda o: (o["last_modified"], o["key"]))

    def _rows(self, reader: io.BufferedReader, sc: S3StreamConfig, key: str):  # noqa: ANN202
        fmt = self._format_for(sc, key)
        assert fmt is not None
        return parse_records(
            reader, fmt, encoding=sc.encoding, csv_delimiter=sc.csv_delimiter, name=key
        )

    @staticmethod
    def _format_for(sc: S3StreamConfig, key: str) -> FileFormat | None:
        if sc.format:
            return sc.format
        return EXT_TO_FORMAT.get(posixpath.splitext(key)[1].lower())


class _RawBody(io.RawIOBase):
    """Adapts a boto3 StreamingBody (or any ``.read(n)`` object) to RawIOBase."""

    def __init__(self, body: Any) -> None:
        self._body = body

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
        chunk = self._body.read(len(b))
        n = len(chunk)
        b[:n] = chunk
        return n

    def close(self) -> None:
        close = getattr(self._body, "close", None)
        if callable(close):
            close()
        super().close()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
