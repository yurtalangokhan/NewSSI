"""ORM model for the ``sync_schedules`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.models.base import Base


class SyncScheduleModel(Base):
    """Cron-based sync schedule definitions.

    Each datasource can have **at most one** schedule
    (enforced by ``uq_datasource_schedule``).
    """

    __tablename__ = "sync_schedules"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    datasource_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        nullable=False,
    )
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    preset: Mapped[str] = mapped_column(
        Text, nullable=False, default="custom", server_default=text("'custom'"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE"),
    )
    update_graph_rag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE"),
    )
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, default="UTC", server_default=text("'UTC'"),
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_run_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    # Back-reference
    datasource: Mapped[PgCollection | None] = relationship(
        "PgCollection",
        back_populates="schedule",
    )

    __table_args__ = (
        UniqueConstraint("datasource_id", name="uq_datasource_schedule"),
        Index(
            "idx_sync_schedules_enabled",
            "enabled",
            postgresql_where=text("enabled = TRUE"),
        ),
        Index(
            "idx_sync_schedules_next_run",
            "next_run_at",
            postgresql_where=text("enabled = TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SyncSchedule id={self.id!s} datasource={self.datasource_id!s} "
            f"enabled={self.enabled}>"
        )
