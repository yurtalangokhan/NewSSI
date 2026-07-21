from typing import Any

from pydantic import BaseModel, Field


class BatchRequest(BaseModel):
    datasource_id: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    connector_type: str | None = None
    stream_name: str = "unknown"
    batch_id: str = ""
    batch_index: int = 0
    is_last_batch: bool = False


class BatchResponse(BaseModel):
    status: str
    batch_index: int
    records_received: int
    chunks_indexed: int
    is_last_batch: bool


class SourcePreviewRequest(BaseModel):
    datasource_id: str
    stream: str | None = None
    limit: int = 20
