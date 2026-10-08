"""Pydantic/DTO schemas for the documents domain: upload pipeline and search."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileUploadDTO:
    """Framework-agnostic representation of an uploaded file.

    The API layer reads bytes from FastAPI ``UploadFile`` and builds one of
    these so that downstream services never depend on FastAPI types.

    Backed by a private temp file rather than raw bytes (spec T4): a batch
    of files near the size limit no longer needs all of them held in
    process memory simultaneously from upload through to the end of
    parsing, since only one file is ever actually being parsed at a time.
    ``content_hash`` is computed once, incrementally, during the bounded
    read that created this file (see ``documents.upload_limits.read_bounded``)
    -- nothing has to re-read it from disk just to hash it for dedup.

    Owns the temp file: call ``cleanup()`` (idempotent) once done with it,
    in a ``finally`` block, so an exception partway through processing
    never leaks it.
    """

    filename: str
    content_type: str | None
    size: int
    path: Path
    content_hash: str

    def cleanup(self) -> None:
        """Remove the backing temp file. Safe to call more than once, and
        safe to call even if the file was already removed.
        """
        self.path.unlink(missing_ok=True)


class UploadStatus(StrEnum):
    """Status of a document upload/embedding job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadProgress(BaseModel):
    """Progress information for a document upload/embedding job."""

    collection_id: str
    status: UploadStatus = UploadStatus.PENDING
    total_files: int = 0
    processed_files: int = 0
    current_file: str | None = None
    total_chunks: int = 0
    processed_chunks: int = 0
    duplicate_files: list[str] = []
    failed_files: list[str] = []
    added_chunk_ids: list[str] = []
    error: str | None = None

    @property
    def progress_percent(self) -> float:
        """Return progress as a percentage."""
        if self.total_chunks == 0:
            return 0.0
        return round((self.processed_chunks / self.total_chunks) * 100, 1)


class UploadJobStartResponse(BaseModel):
    """Response for a document upload job start request."""

    collection_id: str
    status: UploadStatus
    message: str


class SearchQuery(BaseModel):
    """Request body for a document similarity search."""

    query: str
    # Bounded: an unbounded limit let one request pull an entire collection
    # into memory and back over the wire.
    limit: int | None = Field(default=10, ge=1, le=100)
    filter: dict[str, Any] | None = None


class SearchResult(BaseModel):
    """One document search hit."""

    id: str
    page_content: str
    metadata: dict[str, Any] | None = None
    score: float
