"""Models for document upload progress tracking."""

from enum import StrEnum

from pydantic import BaseModel


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
