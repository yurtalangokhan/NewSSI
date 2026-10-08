"""ORM models for versioned, agent-editable documents (drafts)."""

from __future__ import annotations

from datetime import datetime
import uuid as _uuid

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base


class AuthoredDocumentModel(Base):
    __tablename__ = "authored_documents"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("thread.thread_id", ondelete="CASCADE"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    head_revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("ix_authored_documents_user_id", "user_id"),
        Index("ix_authored_documents_thread_id", "thread_id"),
    )


class AuthoredDocumentRevisionModel(Base):
    __tablename__ = "authored_document_revisions"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    document_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authored_documents.id", ondelete="CASCADE"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[_uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    restored_from_revision_id: Mapped[_uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_format: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    edit_ops: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    rendered_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("document_id", "revision_no", name="uq_authored_document_revisions_doc_no"),
        Index("ix_authored_document_revisions_document_id", "document_id"),
        Index("ix_authored_document_revisions_rendered_file_id", "rendered_file_id"),
    )
