"""ORM model for the ``langchain_pg_collection`` table.

``PgCollection`` maps to ``langchain_pg_collection`` which stores
datasource metadata (connector_type, etc.).

.. note::
   The ``langchain_pg_embedding`` table was dropped in migration 0035.
   All embedding / chunk data is stored in Milvus, not Postgres.
"""

from __future__ import annotations

import uuid as _uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db.models.base import Base

if TYPE_CHECKING:
    from core.db.models.airbyte_mapping import AirbyteMappingModel
    from core.db.models.schedule import SyncScheduleModel


class PgCollection(Base):
    """Maps to ``langchain_pg_collection``."""

    __tablename__ = "langchain_pg_collection"

    uuid: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    cmetadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationship — one collection → one schedule (optional)
    schedule: Mapped[SyncScheduleModel | None] = relationship(
        "SyncScheduleModel",
        back_populates="datasource",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Relationship — one collection → one airbyte mapping (optional)
    airbyte_mapping: Mapped[AirbyteMappingModel | None] = relationship(
        "AirbyteMappingModel",
        back_populates="datasource",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<PgCollection uuid={self.uuid!s} name={self.name!r}>"
