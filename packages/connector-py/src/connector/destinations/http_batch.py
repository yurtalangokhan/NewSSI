"""HTTP batch destination.

Every batch is POSTed as JSON to an ingestion endpoint (``base_url`` +
``batch_path``) with this payload::

    {
      "datasource_id": "...", "connector_type": "postgres", "stream_name": "orders",
      "batch_id": "<datasource>:<job>:<stream>:<index>", "records": [...],
      "batch_index": 0, "is_last_batch": false
    }

``batch_id`` is the same when the runner retries a batch, so the receiver can
deduplicate on it. The receiving end is told when a stream is complete: the
closing batch of every stream carries ``is_last_batch`` and is sent even when
it has no records.

Retries are handled by the sync runner: a ``5xx``, ``408`` or ``429`` answer
raises :class:`httpx.HTTPStatusError` and is tried again; any other ``4xx``
means the receiver rejected the payload itself, so the run stops with
:class:`~connector.errors.DestinationWriteError` instead of resending it.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, Field

from ..base import BaseDestination, secret_field, sensitive_mapping_field
from ..errors import DestinationWriteError
from ..models import (
    Batch,
    CheckResult,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    WriteResult,
)


class HttpBatchConfig(BaseModel):
    base_url: str = Field(description="Base URL of the service that receives the batches.")
    batch_path: str = Field(
        description="Path that receives the batch POSTs, e.g. /ingest/batch (no default: nothing "
        "in the platform serves one)."
    )
    health_path: str = Field(default="/health")
    datasource_id: str = Field(description="Identifier forwarded in every payload.")
    connector_type: str = Field(
        default="unknown", description="Source connector type for metadata."
    )
    bearer_token: str | None = secret_field(default=None)
    extra_headers: dict[str, str] = sensitive_mapping_field(default_factory=dict)
    request_timeout_seconds: float = Field(default=120.0, ge=1, le=600)
    stream_field_name: str = Field(
        default="_stream",
        description="Key under which each record carries its stream name (legacy behaviour).",
    )


class HttpBatchDestination(BaseDestination[HttpBatchConfig]):
    definition = ConnectorDefinition(
        name="http_batch",
        icon="http_batch.svg",
        display_name="HTTP Batch Ingestion",
        kind=ConnectorKind.DESTINATION,
        category=ConnectorCategory.API,
        tags=frozenset({"http", "ingest"}),
    )
    Config = HttpBatchConfig
    needs_final_batch: ClassVar[bool] = True

    def __init__(self, config: HttpBatchConfig, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json", **self.config.extra_headers}
            if self.config.bearer_token:
                headers["Authorization"] = f"Bearer {self.config.bearer_token}"
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=self.config.request_timeout_seconds,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def check(self) -> CheckResult:
        try:
            resp = await self._get_client().get(self.config.health_path)
        except httpx.HTTPError as exc:
            return CheckResult(ok=False, message=f"cannot reach {self.config.base_url}: {exc}")
        if resp.status_code >= 400:
            return CheckResult(
                ok=False, message=f"health endpoint returned HTTP {resp.status_code}"
            )
        return CheckResult(ok=True)

    async def write(self, batch: Batch) -> WriteResult:
        payload = self.build_payload(batch)
        resp = await self._get_client().post(self.config.batch_path, json=payload)
        if resp.status_code >= 400:
            message = f"batch POST returned {resp.status_code}: {resp.text[:300]}"
            if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                raise DestinationWriteError(message)  # rejected payload: retrying cannot help
            raise httpx.HTTPStatusError(message, request=resp.request, response=resp)
        body: dict[str, Any] = {}
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {}
        return WriteResult(
            records_written=batch.size, extra={"chunks_indexed": body.get("chunks_indexed", 0)}
        )

    def build_payload(self, batch: Batch) -> dict[str, Any]:
        key = self.config.stream_field_name
        records = [{**r.data, key: batch.stream} if key else dict(r.data) for r in batch.records]
        parts = (self.config.datasource_id, batch.job_id, batch.stream, str(batch.batch_index))
        return {
            "datasource_id": self.config.datasource_id,
            "connector_type": self.config.connector_type,
            "stream_name": batch.stream,
            "batch_id": ":".join(p for p in parts if p),
            "records": records,
            "batch_index": batch.batch_index,
            "is_last_batch": batch.is_last,
        }
