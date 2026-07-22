"""ORM model for the ``document`` table.

Documents are files (PDF, DOCX, images, CSV, …) uploaded through the
chat UI or attached to a project.  The raw bytes live in MinIO; this
table holds the metadata needed to retrieve and serve them.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class DocumentModel(Base):
    """Uploaded document metadata pointing to a MinIO object."""

    __tablename__ = "document"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    # Hex token used as the file_id throughout the app (matches FileService key)
    file_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    chat_file_type: Mapped[str] = mapped_column(Text, nullable=False, default="document")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minio_object_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional scope — a document belongs to a thread, a project, or both
    thread_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thread.thread_id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_document_user_id", "user_id"),
        Index("ix_document_thread_id", "thread_id"),
        Index("ix_document_project_id", "project_id"),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id!s} file_id={self.file_id!r} filename={self.filename!r}>"
