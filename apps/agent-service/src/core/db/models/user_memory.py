"""Legacy ORM model for the ``user_memory`` table in agent-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class UserMemoryModel(Base):
    """Legacy memory table kept for migration compatibility."""

    __tablename__ = "user_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
        server_default=text("'manual'"),
    )
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    time_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("idx_user_memory_user_id", "user_id", text("time_created DESC")),
        Index("uq_user_memory_user_content_lower", "user_id", func.lower(content), unique=True),
    )
