"""
Pydantic request / response models.

All Pydantic models used across the service routes are
collected here to avoid circular imports and duplication.
"""
from typing import Any, Dict, List, Optional

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
    metadata: Optional[Dict] = None
    graph_id: Optional[str] = None


class AssistantCreateRequest(BaseModel):
    """Request model for creating an assistant."""
    graph_id: str
    name: Optional[str] = None
    config: Optional[Dict] = None
    metadata: Optional[Dict] = None


class AssistantUpdateRequest(BaseModel):
    """Request model for updating an assistant."""
    name: Optional[str] = None
    config: Optional[Dict] = None
    metadata: Optional[Dict] = None


# =============================================================================
# Thread models
# =============================================================================

class ThreadSearchRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    metadata: Optional[Dict] = None


class ThreadCreateRequest(BaseModel):
    thread_id: Optional[str] = None
    metadata: Optional[Dict] = None


class ThreadUpdateRequest(BaseModel):
    metadata: Optional[Dict] = None


class ThreadState(BaseModel):
    values: Dict[str, Any]
    next: List[str]
    checkpoint: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    parent_config: Optional[Dict[str, Any]] = None
    parent_checkpoint: Optional[Dict[str, Any]] = None  # For SDK compatibility


class ThreadHistoryRequest(BaseModel):
    limit: int = 10
    before: Optional[str] = None
    metadata: Optional[Dict] = None
    checkpoint: Optional[Dict] = None


# =============================================================================
# Run models
# =============================================================================

class RunCreate(BaseModel):
    """Request model for creating a run."""
    assistant_id: str
    input: Optional[Dict[str, Any]] = None
    command: Optional[Dict[str, Any]] = None  # SDK sends {resume: value} for interrupt resumption
    config: Optional[Dict[str, Any]] = None
    stream_mode: Optional[List[str]] = ["values"]
    interrupt_before: Optional[List[str]] = None
    interrupt_after: Optional[List[str]] = None
    webhook: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    multitask_strategy: Optional[str] = None
    on_completion: Optional[str] = None
    on_disconnect: Optional[str] = None
    after_seconds: Optional[int] = None


class RunCancel(BaseModel):
    """Request model for cancelling a run."""
    wait: bool = False
    action: Optional[str] = "interrupt"  # "interrupt" or "rollback"


# =============================================================================
# Data-source / Connector models  (moved from datasources.py)
# =============================================================================

class AirbyteConnectorConfig(BaseModel):
    """Configuration for an Airbyte-based data source."""
    connector_type: str = Field(..., description="Airbyte connector name, e.g., 'source-postgres'")
    connector_config: Dict[str, Any] = Field(..., description="Connector-specific configuration (native nested JSON)")
    streams: Optional[List[str]] = Field(None, description="Specific streams to sync, None = all")
    content_fields: Optional[List[str]] = Field(None, description="Fields to include in document content")


class DataSourceInput(BaseModel):
    """Input for creating a new data source."""
    name: str = Field(..., description="Human-readable name for the data source")
    config: AirbyteConnectorConfig


class DataSourceUpdateInput(BaseModel):
    """Input for updating an existing data source."""
    name: Optional[str] = Field(None, description="New human-readable name")
    connector_config: Optional[Dict[str, Any]] = Field(None, description="Updated connector configuration (native nested JSON)")
    streams: Optional[List[str]] = Field(None, description="Updated list of streams to sync")
    sync_mode: Optional[str] = Field(None, description="Sync mode: full_refresh or incremental")
    destination_sync_mode: Optional[str] = Field(None, description="Destination sync mode: overwrite or append")


class DataSourceResponse(BaseModel):
    """Response model for a data source."""
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    streams: Optional[List[str]] = None
    sync_status: Optional[str] = None
    sync_progress: Optional[int] = None
    document_count: int = 0
    created_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    schedule_summary: Optional[Dict[str, Any]] = None


class ChunkInfo(BaseModel):
    """Information about a single chunk in the vector store."""
    content: str
    char_count: int = 0
    token_count: int = 0
    word_count: int = 0
    source: Optional[str] = None
    stream: Optional[str] = None
    connector_type: Optional[str] = None
    metadata: Dict[str, Any] = {}


class DataSourceDetails(BaseModel):
    """Detailed information about a data source."""
    id: str
    name: str
    connector_type: str
    connector_display_name: str
    config: Dict[str, Any]  # Masked sensitive fields
    streams: Optional[List[str]] = None
    available_streams: Optional[List[str]] = None
    sync_status: Optional[str] = None
    sync_progress: Optional[int] = None
    document_count: int = 0
    chunk_count: int = 0
    chunks: List[ChunkInfo] = []
    avg_chunk_tokens: Optional[int] = None
    avg_chunk_chars: Optional[int] = None
    sample_documents: List[Dict[str, Any]] = []  # Kept for backward compat
    created_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    last_error: Optional[str] = None
    sync_mode: Optional[str] = None
    destination_sync_mode: Optional[str] = None
    schedule: Optional[Dict[str, Any]] = None
    graph_rag_available: bool = False


class ConnectorInfoResponse(BaseModel):
    """Information about an available connector."""
    name: str
    display_name: str
    source_definition_id: str
    category: Optional[str] = None


class ConnectorSpecResponse(BaseModel):
    """Raw JSON Schema specification for a connector."""
    name: str
    display_name: str
    source_definition_id: str
    connection_specification: Dict[str, Any]
    documentation_url: Optional[str] = None


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
    category: Optional[str] = None
    icon_url: Optional[str] = None
    documentation_url: Optional[str] = None
    is_available: bool = True


class ConnectorSpec(BaseModel):
    """Raw JSON Schema specification for a connector.

    ``connection_specification`` contains the **raw** JSON Schema as
    returned by the Airbyte API — **NO** flattening, **NO** transformation.
    """
    name: str
    source_definition_id: str
    connection_specification: Dict[str, Any]
    documentation_url: Optional[str] = None


# =============================================================================
# Ingestion models  (moved from ingest_routes.py)
# =============================================================================

class BatchRequest(BaseModel):
    """A single batch of records from destination-embedding."""
    datasource_id: str = Field(..., description="UUID of the target collection")
    records: List[Dict[str, Any]] = Field(default_factory=list, description="Raw records from Airbyte source")
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
    stream: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
