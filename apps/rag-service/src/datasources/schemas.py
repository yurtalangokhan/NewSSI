"""Datasource request and result schemas."""

from typing import Any

from pydantic import BaseModel, Field


class DatasourceRecordIn(BaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    #: Identity of the record at its source (a SHA-1 in hex). The chunks an
    #: earlier write stored under the same key are replaced; a document
    #: without a key is appended.
    record_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")


class DatasourceRecordsIngestRequest(BaseModel):
    documents: list[DatasourceRecordIn] = Field(default_factory=list)
    clear_existing: bool = False


class KnowledgeSelectorResponse(BaseModel):
    document_processing: list[dict[str, Any]]
    knowledge_graph: list[dict[str, Any]]


class DatasourceRecordsIngestResponse(BaseModel):
    chunks_indexed: int
    chunk_char_total: int
    chunk_token_total: int
    #: Chunks an earlier write had stored under the batch's record keys.
    chunks_replaced: int = 0


class DatasourceRecordsRetireRequest(BaseModel):
    #: The sync run whose chunks stay; every other chunk of the collection goes.
    #: A job id as the records' metadata ``_sync_job_id`` carries it.
    keep_job_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")


class DatasourceRecordsRetireResponse(BaseModel):
    chunks_removed: int


class DatasourceRecordsDeleteResponse(BaseModel):
    #: Entities the dropped Milvus table held; ``0`` when nothing was ever written.
    chunks_removed: int


class DatasourceEntitiesResponse(BaseModel):
    count: int
    entities: list[dict[str, Any]]
    stats: dict[str, int] | None = None
