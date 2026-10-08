"""Amazon S3 destination: lands every batch as one JSON Lines object.

Layout::

    {prefix}/{stream}/{run_id}/part-00000.jsonl[.gz]
    {prefix}/{stream}/{run_id}/_manifest.json      (written by ``finalize``)

* ``run_id`` is a UTC timestamp taken in ``begin``; batch indices restart at 0
  every sync, so the run folder keeps appends from clobbering earlier runs.
* ``overwrite`` streams have every other run folder under ``{prefix}/{stream}/``
  deleted in ``finalize``, after the new run's manifest is written: the previous
  run stays readable until the new one is complete, and a run that fails
  leaves the previous one in place. ``append`` streams keep prior runs.
* Writes are idempotent per ``(run, stream, batch_index)``: a retried batch
  rewrites the same key and is counted once in the manifest.
* A run that stops early leaves its part files without a manifest, which is how
  a reader tells a complete run from an incomplete one. Those parts are data all
  the same: for an incremental stream their checkpoints were stored as they
  were written, so the next run continues after them and does not write them
  again. Hence no ``abort`` that would delete them.

boto3 is synchronous; calls are offloaded with ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, TypeVar

from pydantic import BaseModel, Field

from ..base import BaseDestination
from ..common.s3_connection import AwsConnection, build_s3_client
from ..models import (
    Batch,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    DestinationSyncMode,
    WriteResult,
)


class S3DestinationOptions(BaseModel):
    """Where and how to write; independent of how the object store is reached."""

    bucket: str
    prefix: str = Field(default="", description="Key prefix (folder) for all written objects.")
    compression: Literal["none", "gzip"] = "none"
    include_metadata: bool = Field(
        default=True, description="Add `_stream` and `_emitted_at` to every written row."
    )
    write_manifest: bool = True

    def client_kwargs(self) -> dict[str, Any]:
        """boto3 client arguments. Supplied by the connection model a config is combined with."""
        raise NotImplementedError


class S3DestinationConfig(AwsConnection, S3DestinationOptions):
    """Amazon S3 destination configuration."""


S3DestConfigT = TypeVar("S3DestConfigT", bound=S3DestinationOptions)


class S3Destination(BaseDestination[S3DestConfigT]):
    definition = ConnectorDefinition(
        name="s3",
        display_name="Amazon S3",
        kind=ConnectorKind.DESTINATION,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://docs.aws.amazon.com/s3/",
        icon="s3.svg",
        tags=frozenset({"file", "cloud", "storage"}),
    )
    Config: ClassVar[type[BaseModel]] = S3DestinationConfig
    extra_name = "s3"

    def __init__(self, config: S3DestConfigT, client: Any | None = None) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None
        self._run_id: str = _new_run_id()
        self._written: dict[str, dict[int, int]] = {}  # stream -> batch index -> records

    # ---- client -----------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = build_s3_client(self.config.client_kwargs(), extra_name=self.extra_name)
        return self._client

    async def close(self) -> None:
        """Close the client this destination built; an injected one stays."""
        if self._client is not None and self._owns_client:
            close = getattr(self._client, "close", None)
            if close is not None:
                await asyncio.to_thread(close)
            self._client = None

    # ---- keys ---------------------------------------------------------------------

    def _stream_prefix(self, stream: str) -> str:
        base = self.config.prefix.strip("/")
        return f"{base}/{stream}/" if base else f"{stream}/"

    def _run_prefix(self, stream: str) -> str:
        return f"{self._stream_prefix(stream)}{self._run_id}/"

    def _part_key(self, stream: str, index: int) -> str:
        ext = "jsonl.gz" if self.config.compression == "gzip" else "jsonl"
        return f"{self._run_prefix(stream)}part-{index:05d}.{ext}"

    # ---- connector API --------------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            await asyncio.to_thread(
                lambda: self._get_client().head_bucket(Bucket=self.config.bucket)
            )
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def begin(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        self._run_id = _new_run_id()
        self._written = {}

    async def write(self, batch: Batch) -> WriteResult:
        written = self._written.setdefault(batch.stream, {})
        if not batch.records:
            return WriteResult(records_written=0)
        body = self._encode(batch)
        key = self._part_key(batch.stream, batch.batch_index)
        await asyncio.to_thread(self._put, key, body, self._content_type())
        written[batch.batch_index] = batch.size  # a retried batch replaces its own entry
        return WriteResult(records_written=batch.size, extra={"key": key, "bytes": len(body)})

    async def finalize(
        self,
        catalog: ConfiguredCatalog,
        connection_id: str | None = None,
        *,
        job_id: str | None = None,
    ) -> None:
        """Write the manifests, then retire the older runs of ``overwrite`` streams.

        A run folder without a manifest was not completed. The sweep comes after the
        manifest so the previous run stays readable until this one is complete.
        """
        for configured in catalog.streams:
            name = configured.stream.name
            if self.config.write_manifest:
                written = self._written.get(name, {})
                manifest = {
                    "stream": name,
                    "run_id": self._run_id,
                    "connection_id": connection_id,
                    "job_id": job_id,
                    "sync_mode": configured.sync_mode.value,
                    "destination_sync_mode": configured.destination_sync_mode.value,
                    "records": sum(written.values()),
                    "objects": len(written),
                    "compression": self.config.compression,
                    "finished_at": datetime.now(UTC).isoformat(),
                }
                key = f"{self._run_prefix(name)}_manifest.json"
                body = json.dumps(manifest, indent=2).encode()
                await asyncio.to_thread(self._put, key, body, "application/json")
            if configured.destination_sync_mode is DestinationSyncMode.OVERWRITE:
                await asyncio.to_thread(
                    self._delete_prefix, self._stream_prefix(name), keep=self._run_prefix(name)
                )

    # ---- internals ----------------------------------------------------------------------

    def _encode(self, batch: Batch) -> bytes:
        lines = []
        for record in batch.records:
            row = dict(record.data)
            if self.config.include_metadata:
                row.setdefault("_stream", batch.stream)
                row.setdefault("_emitted_at", record.emitted_at.isoformat())
            lines.append(json.dumps(row, default=str, ensure_ascii=False))
        raw = ("\n".join(lines) + "\n").encode("utf-8")
        return gzip.compress(raw) if self.config.compression == "gzip" else raw

    def _content_type(self) -> str:
        return "application/gzip" if self.config.compression == "gzip" else "application/x-ndjson"

    def _put(self, key: str, body: bytes, content_type: str) -> None:
        self._get_client().put_object(
            Bucket=self.config.bucket, Key=key, Body=body, ContentType=content_type
        )

    def _delete_prefix(self, prefix: str, *, keep: str | None = None) -> int:
        """Delete every object under ``prefix`` except those under ``keep``."""
        client = self._get_client()
        deleted = 0
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.config.bucket, Prefix=prefix):
            keys = [
                {"Key": o["Key"]}
                for o in page.get("Contents", []) or []
                if not (keep and o["Key"].startswith(keep))
            ]
            for i in range(0, len(keys), 1000):  # DeleteObjects accepts at most 1000 keys
                chunk = keys[i : i + 1000]
                client.delete_objects(Bucket=self.config.bucket, Delete={"Objects": chunk})
                deleted += len(chunk)
        return deleted


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
