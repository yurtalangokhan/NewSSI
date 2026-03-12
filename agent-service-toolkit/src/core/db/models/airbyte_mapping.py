"""ORM model for the ``datasource_airbyte_mapping`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.models.base import Base


class AirbyteMappingModel(Base):
    """Links local datasource UUIDs to Airbyte platform IDs.

    Tracks which Airbyte source / connection / destination correspond
    to each datasource, plus a ``last_processed_job_id`` watermark
    for the sync listener.
    """

    __tablename__ = "datasource_airbyte_mapping"

    datasource_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        primary_key=True,
    )
    airbyte_source_id: Mapped[str] = mapped_column(String, nullable=False)
    airbyte_connection_id: Mapped[str] = mapped_column(String, nullable=False)
    airbyte_destination_id: Mapped[str] = mapped_column(String, nullable=False)
    update_graph_rag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE"),
    )
    last_processed_job_id: Mapped[int] = mapped_column(
        BIGINT, nullable=False, default=0, server_default=text("0"),
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

    # Back-reference
    datasource: Mapped["PgCollection | None"] = relationship(
        "PgCollection",
        back_populates="airbyte_mapping",
    )

    def __repr__(self) -> str:
        return (
            f"<AirbyteMapping datasource={self.datasource_id!s} "
            f"connection={self.airbyte_connection_id!r}>"
        )
