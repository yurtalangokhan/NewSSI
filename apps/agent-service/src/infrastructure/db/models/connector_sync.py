"""ORM models for connector sync bookkeeping: jobs and incremental state."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid as _uuid

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.models.base import Base

#: Statuses of a job that has not finished (connector-py ``JobStatus``).
ACTIVE_STATUSES = ("pending", "running")
#: The rows those are, as SQL. The unique index below, migration ``0052`` and the
#: ``ON CONFLICT`` of ``ConnectorSyncJobRepository.create_exclusive`` must spell
#: one and the same predicate, or PostgreSQL does not match the index.
ACTIVE_JOB_PREDICATE = "status IN ({})".format(", ".join(f"'{status}'" for status in ACTIVE_STATUSES))
#: At most one job of a datasource is pending or running at a time.
ACTIVE_JOB_INDEX = "uq_connector_sync_jobs_active"


class ConnectorSyncJobModel(Base):
    """One sync run of a datasource (connector-py ``Job``).

    ``heartbeat_at`` is refreshed while the job is alive, so a job left
    ``pending``/``running`` by a dead process can be told apart from a live one.
    """

    __tablename__ = "connector_sync_jobs"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    datasource_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="manual",
        server_default=text("'manual'"),
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_connector_sync_jobs_datasource_created", "datasource_id", "created_at"),
        Index(
            "idx_connector_sync_jobs_active",
            "status",
            postgresql_where=text(ACTIVE_JOB_PREDICATE),
        ),
        Index(
            ACTIVE_JOB_INDEX,
            "datasource_id",
            unique=True,
            postgresql_where=text(ACTIVE_JOB_PREDICATE),
        ),
    )

    def __repr__(self) -> str:
        return f"<ConnectorSyncJob id={self.id!s} datasource={self.datasource_id!s} status={self.status!r}>"


class ConnectorSyncStateModel(Base):
    """Incremental checkpoints of a datasource (connector-py ``SyncState``)."""

    __tablename__ = "connector_sync_state"

    datasource_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    def __repr__(self) -> str:
        return f"<ConnectorSyncState datasource={self.datasource_id!s}>"
