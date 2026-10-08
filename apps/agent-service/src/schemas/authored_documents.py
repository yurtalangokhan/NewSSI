"""HTTP DTOs for versioned document drafts.

Each DTO gets a ``from_domain`` classmethod so mapping stays out of the route
bodies (routes only parse input, call one service method, and map the
result). Field names mirror ``core.types.authored_documents`` so
``from_attributes`` can also be used directly where a dataclass is passed in
as-is; ``from_domain`` is preferred because it also flattens nested value
objects (``RevisionStats``, ``StoredFileRef``) into plain DTOs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from core.types.authored_documents import (
    MAX_DOCUMENT_CONTENT_CHARS,
    MAX_REVISION_NO,
    MAX_REVISION_SUMMARY_CHARS,
    AuthoredDocument,
    Revision,
    RevisionResult,
    RevisionStats,
    RevisionSummary,
    StoredFileRef,
)


class RevisionStatsDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    added: int
    removed: int
    changes: list[dict[str, str]]

    @classmethod
    def from_domain(cls, stats: RevisionStats) -> RevisionStatsDTO:
        return cls(added=stats.added, removed=stats.removed, changes=[c.to_dict() for c in stats.changes])


class RevisionSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_no: int
    operation: str
    author_type: str
    summary: str
    format: str
    stats: RevisionStatsDTO
    rendered_file_id: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, summary: RevisionSummary) -> RevisionSummaryDTO:
        return cls(
            revision_no=summary.revision_no,
            operation=summary.operation.value,
            author_type=summary.author_type.value,
            summary=summary.summary,
            format=summary.format,
            stats=RevisionStatsDTO.from_domain(summary.stats),
            rendered_file_id=summary.rendered_file_id,
            created_at=summary.created_at,
        )


class RevisionDetailDTO(RevisionSummaryDTO):
    document_id: UUID
    source_format: str
    content: str
    options: dict[str, Any]
    title: str | None
    filename: str

    @classmethod
    def from_domain(cls, revision: Revision) -> RevisionDetailDTO:  # type: ignore[override]
        return cls(
            revision_no=revision.revision_no,
            operation=revision.operation.value,
            author_type=revision.author_type.value,
            summary=revision.summary,
            format=revision.format,
            stats=RevisionStatsDTO.from_domain(revision.stats),
            rendered_file_id=revision.rendered_file_id,
            created_at=revision.created_at,
            document_id=revision.document_id,
            source_format=revision.source_format.value,
            content=revision.content,
            options=revision.options,
            title=revision.title,
            filename=revision.filename,
        )


class DocumentSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    kind: str
    title: str | None
    filename: str
    format: str
    head_revision_no: int
    thread_id: UUID | None
    updated_at: datetime

    @classmethod
    def from_domain(cls, document: AuthoredDocument) -> DocumentSummaryDTO:
        return cls(
            document_id=document.id,
            kind=document.kind.value,
            title=document.title,
            filename=document.filename,
            format=document.format,
            head_revision_no=document.head_revision_no,
            thread_id=document.thread_id,
            updated_at=document.updated_at,
        )


class DocumentDetailDTO(DocumentSummaryDTO):
    revisions: list[RevisionSummaryDTO]

    @classmethod
    def from_domain(  # type: ignore[override]
        cls, document: AuthoredDocument, revisions: list[RevisionSummary]
    ) -> DocumentDetailDTO:
        return cls(
            document_id=document.id,
            kind=document.kind.value,
            title=document.title,
            filename=document.filename,
            format=document.format,
            head_revision_no=document.head_revision_no,
            thread_id=document.thread_id,
            updated_at=document.updated_at,
            revisions=[RevisionSummaryDTO.from_domain(r) for r in revisions],
        )


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummaryDTO]


class FileDocumentRefDTO(BaseModel):
    document_id: UUID
    revision_no: int
    head_revision_no: int

    @classmethod
    def from_domain(cls, document: AuthoredDocument, revision_summary: RevisionSummary) -> FileDocumentRefDTO:
        return cls(
            document_id=document.id,
            revision_no=revision_summary.revision_no,
            head_revision_no=document.head_revision_no,
        )


class UserRevisionRequest(BaseModel):
    base_revision_no: int = Field(ge=1, le=MAX_REVISION_NO)
    content: str = Field(max_length=MAX_DOCUMENT_CONTENT_CHARS)
    summary: str = Field(default="", max_length=MAX_REVISION_SUMMARY_CHARS)


class RestoreRequest(BaseModel):
    base_revision_no: int = Field(ge=1, le=MAX_REVISION_NO)


class RenderedFileRefDTO(BaseModel):
    file_id: str
    filename: str
    mime_type: str
    size_bytes: int
    download_url: str

    @classmethod
    def from_domain(cls, file_ref: StoredFileRef) -> RenderedFileRefDTO:
        return cls(
            file_id=file_ref.file_id,
            filename=file_ref.filename,
            mime_type=file_ref.mime_type,
            size_bytes=file_ref.size_bytes,
            download_url=file_ref.download_url,
        )


class RevisionMutationResponse(BaseModel):
    document: DocumentSummaryDTO
    revision: RevisionSummaryDTO
    file: RenderedFileRefDTO
    diagram_check: str

    @classmethod
    def from_domain(cls, result: RevisionResult) -> RevisionMutationResponse:
        return cls(
            document=DocumentSummaryDTO.from_domain(result.document),
            revision=RevisionSummaryDTO.from_domain(result.revision),
            file=RenderedFileRefDTO.from_domain(result.file),
            diagram_check=result.diagram_check.value,
        )
