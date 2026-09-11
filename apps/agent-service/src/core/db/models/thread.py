"""ORM model for the ``thread`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base
from core.run_kinds import DEFAULT_RUN_KIND


class ThreadModel(Base):
    """Conversation threads with JSONB metadata.

    Each thread tracks its status (idle / busy / …) and stores
    arbitrary metadata used for filtering (e.g. ``user_id``).
    """

    __tablename__ = "thread"

    thread_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="idle",
    )
    run_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DEFAULT_RUN_KIND.value,
        server_default=text(f"'{DEFAULT_RUN_KIND.value}'"),
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_thread_metadata_gin", metadata_, postgresql_using="gin"),
        Index(
            "idx_thread_activity_order",
            text("COALESCE(last_message_at, created_at) DESC"),
            text("thread_id DESC"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Thread id={self.thread_id!s} status={self.status!r}>"
