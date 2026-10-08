from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorConfigInput(BaseModel):
    connector_type: str
    connector_config: dict[str, Any]
    streams: list[str] | None = None
    content_fields: list[str] | None = None


class DataSourceInput(BaseModel):
    name: str
    config: ConnectorConfigInput


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


class ConnectorCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    connectors: list[dict[str, Any]] | None = None
    categories: list[str] | None = None
    category_labels: dict[str, str] | None = None
    by_category: dict[str, list[dict[str, Any]]] | None = None
    category: str | None = None
    total: int = 0


class ConnectorValidationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    valid: bool
    message: str


class DatasourceSyncStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    id: str


class DatasourceScheduleInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    cron_expression: str | None = None
    next_run_at: str | None = None
    update_graph_rag: bool = False


class DatasourceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    sync_status: str = "idle"
    sync_progress: int | float = 0
    last_synced_at: str | None = None
    last_error: str | None = None
    graph_update_status: str | None = None
    queue_position: int | None = None
    is_active: bool = False
    schedule: DatasourceScheduleInfo | None = None


class DatasourceSyncJobHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    status: str = "unknown"
    created_at: int | str | None = None
    updated_at: int | str | None = None
    duration_seconds: int | None = None
    bytes_synced: int = 0
    records_synced: int = 0
    error_message: str | None = None
