from typing import Any

from pydantic import BaseModel, Field


class AirbyteConnectorConfig(BaseModel):
    connector_type: str
    connector_config: dict[str, Any]
    streams: list[str] | None = None
    content_fields: list[str] | None = None


class DataSourceInput(BaseModel):
    name: str
    config: AirbyteConnectorConfig


class DataSourceUpdateInput(BaseModel):
    name: str | None = None
    connector_config: dict[str, Any] | None = None
    streams: list[str] | None = None
    sync_mode: str | None = None
    destination_sync_mode: str | None = None


class DataSourceResponse(BaseModel):
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    streams: list[str] | None = None
    sync_status: str | None = None
    sync_progress: int | None = None
    document_count: int = 0
    created_at: str | None = None
    last_synced_at: str | None = None
    schedule_summary: dict[str, Any] | None = None


class ChunkInfo(BaseModel):
    content: str
    char_count: int = 0
    token_count: int = 0
    word_count: int = 0
    source: str | None = None
    stream: str | None = None
    connector_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataSourceDetails(BaseModel):
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    config: dict[str, Any]
    streams: list[str] | None = None
    available_streams: list[str] | None = None
    sync_status: str | None = None
    sync_progress: int | None = None
    document_count: int = 0
    chunk_count: int = 0
    chunks: list[ChunkInfo] = Field(default_factory=list)
    avg_chunk_tokens: int | None = None
    avg_chunk_chars: int | None = None
    sample_documents: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    last_synced_at: str | None = None
    last_error: str | None = None
    sync_mode: str | None = None
    destination_sync_mode: str | None = None
    schedule: dict[str, Any] | None = None
    graph_rag_available: bool = False
