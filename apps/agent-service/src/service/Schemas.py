"""
Pydantic request / response models.

All Pydantic models used across the service routes are
collected here to avoid circular imports and duplication.
"""
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    # Assistant
    "AssistantSearchRequest",
    "AssistantCreateRequest",
    "AssistantUpdateRequest",
    # Thread
    "ThreadSearchRequest",
    "ThreadCreateRequest",
    "ThreadUpdateRequest",
    "ThreadState",
    "ThreadHistoryRequest",
    # Run
    "RunCreate",
    "RunCancel",
    # Data-source / Connector
    "AirbyteConnectorConfig",
    "DataSourceInput",
    "DataSourceUpdateInput",
    "DataSourceResponse",
    "ChunkInfo",
    "DataSourceDetails",
    "ConnectorInfoResponse",
    "ConnectorSpecResponse",
    "StreamInfo",
    # Airbyte connector internals
    "ConnectorInfo",
    "ConnectorSpec",
    # Ingestion
    "BatchRequest",
    "BatchResponse",
    "SourcePreviewRequest",
]


# =============================================================================
# Assistant models
# =============================================================================

class AssistantSearchRequest(BaseModel):
    """Request model for assistant search."""
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None
    graph_id: str | None = None


class AssistantCreateRequest(BaseModel):
    """Request model for creating an assistant."""
    graph_id: str
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None


class AssistantUpdateRequest(BaseModel):
    """Request model for updating an assistant."""
    name: str | None = None
    config: dict | None = None
    metadata: dict | None = None


# =============================================================================
# Thread models
# =============================================================================

class ThreadSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: dict | None = None


class ThreadCreateRequest(BaseModel):
    thread_id: str | None = None
    metadata: dict | None = None


class ThreadUpdateRequest(BaseModel):
    metadata: dict | None = None


class ThreadState(BaseModel):
    values: dict[str, Any]
    next: list[str]
    checkpoint: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    parent_config: dict[str, Any] | None = None
    parent_checkpoint: dict[str, Any] | None = None  # For SDK compatibility


class ThreadHistoryRequest(BaseModel):
    limit: int = 10
    before: str | None = None
    metadata: dict | None = None
    checkpoint: dict | None = None


# =============================================================================
# Run models
# =============================================================================

class RunCreate(BaseModel):
    """Request model for creating a run."""
    assistant_id: str
    input: dict[str, Any] | None = None
    command: dict[str, Any] | None = None  # SDK sends {resume: value} for interrupt resumption
    config: dict[str, Any] | None = None
    stream_mode: list[str] | None = ["values"]
    interrupt_before: list[str] | None = None
    interrupt_after: list[str] | None = None
    webhook: str | None = None
    checkpoint: dict[str, Any] | None = None
    checkpoint_id: str | None = None
    multitask_strategy: str | None = None
    on_completion: str | None = None
    on_disconnect: str | None = None
    after_seconds: int | None = None


class RunCancel(BaseModel):
    """Request model for cancelling a run."""
    wait: bool = False
    action: str | None = "interrupt"  # "interrupt" or "rollback"


# =============================================================================
# Data-source / Connector models  (moved from datasources.py)
# =============================================================================

class AirbyteConnectorConfig(BaseModel):
    """Configuration for an Airbyte-based data source."""
    connector_type: str = Field(..., description="Airbyte connector name, e.g., 'source-postgres'")
    connector_config: dict[str, Any] = Field(..., description="Connector-specific configuration (native nested JSON)")
    streams: list[str] | None = Field(None, description="Specific streams to sync, None = all")
    content_fields: list[str] | None = Field(None, description="Fields to include in document content")


class DataSourceInput(BaseModel):
    """Input for creating a new data source."""
    name: str = Field(..., description="Human-readable name for the data source")
    config: AirbyteConnectorConfig


class DataSourceUpdateInput(BaseModel):
    """Input for updating an existing data source."""
    name: str | None = Field(None, description="New human-readable name")
    connector_config: dict[str, Any] | None = Field(None, description="Updated connector configuration (native nested JSON)")
    streams: list[str] | None = Field(None, description="Updated list of streams to sync")
    sync_mode: str | None = Field(None, description="Sync mode: full_refresh or incremental")
    destination_sync_mode: str | None = Field(None, description="Destination sync mode: overwrite or append")


class DataSourceResponse(BaseModel):
    """Response model for a data source."""
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
    """Information about a single chunk in the vector store."""
    content: str
    char_count: int = 0
    token_count: int = 0
    word_count: int = 0
    source: str | None = None
    stream: str | None = None
    connector_type: str | None = None
    metadata: dict[str, Any] = {}


class DataSourceDetails(BaseModel):
    """Detailed information about a data source."""
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    config: dict[str, Any]  # Masked sensitive fields
    streams: list[str] | None = None
    available_streams: list[str] | None = None
    sync_status: str | None = None
    sync_progress: int | None = None
    document_count: int = 0
    chunk_count: int = 0
    chunks: list[ChunkInfo] = []
    avg_chunk_tokens: int | None = None
    avg_chunk_chars: int | None = None
    sample_documents: list[dict[str, Any]] = []  # Kept for backward compat
    created_at: str | None = None
    last_synced_at: str | None = None
    last_error: str | None = None
    sync_mode: str | None = None
    destination_sync_mode: str | None = None
    schedule: dict[str, Any] | None = None
    graph_rag_available: bool = False


class ConnectorInfoResponse(BaseModel):
    """Information about an available connector."""
    name: str
    display_name: str
    source_definition_id: str
    category: str | None = None


class ConnectorSpecResponse(BaseModel):
    """Raw JSON Schema specification for a connector."""
    name: str
    display_name: str
    source_definition_id: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None


class StreamInfo(BaseModel):
    """Information about an available stream."""
    name: str


# =============================================================================
# Airbyte connector models  (moved from airbyte_connector.py)
# =============================================================================

class ConnectorInfo(BaseModel):
    """Information about an Airbyte connector."""
    name: str
    display_name: str
    source_definition_id: str
    category: str | None = None
    icon_url: str | None = None
    documentation_url: str | None = None
    is_available: bool = True


class ConnectorSpec(BaseModel):
    """Raw JSON Schema specification for a connector.

    ``connection_specification`` contains the **raw** JSON Schema as
    returned by the Airbyte API — **NO** flattening, **NO** transformation.
    """
    name: str
    source_definition_id: str
    connection_specification: dict[str, Any]
    documentation_url: str | None = None


# =============================================================================
# Ingestion models  (moved from ingest_routes.py)
# =============================================================================

class BatchRequest(BaseModel):
    """A single batch of records from destination-embedding."""
    datasource_id: str = Field(..., description="UUID of the target collection")
    records: list[dict[str, Any]] = Field(default_factory=list, description="Raw records from Airbyte source")
    batch_index: int = Field(0, description="Sequential batch number (0-based)")
    is_last_batch: bool = Field(False, description="True if this is the final batch in the sync")


class BatchResponse(BaseModel):
    """Response after processing a batch."""
    status: str
    batch_index: int
    records_received: int
    chunks_indexed: int
    is_last_batch: bool


class SourcePreviewRequest(BaseModel):
    """Request to fetch sample data from the original source."""
    datasource_id: str
    stream: str | None = None
    limit: int = Field(20, ge=1, le=100)
