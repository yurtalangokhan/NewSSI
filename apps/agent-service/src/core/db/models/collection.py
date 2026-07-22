"""ORM models for the LangChain PGVector tables.

``PgCollection`` and ``PgEmbedding`` map to ``langchain_pg_collection``
and ``langchain_pg_embedding`` respectively.

.. note::
   ``langchain_pg_collection.cmetadata`` uses ``JSON``, while
   ``langchain_pg_embedding.cmetadata`` uses ``JSONB``.
"""

from __future__ import annotations

import uuid as _uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
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

    # Relationship — one collection → many embeddings
    embeddings: Mapped[list[PgEmbedding]] = relationship(
        "PgEmbedding",
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

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


class PgEmbedding(Base):
    """Maps to ``langchain_pg_embedding``."""

    __tablename__ = "langchain_pg_embedding"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    collection_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("langchain_pg_collection.uuid", ondelete="CASCADE"),
        nullable=True,
    )
    # ``vector`` type is managed by pgvector — we map as Text so
    # SQLAlchemy doesn't complain; raw embeddings are handled by PGVector.
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    document: Mapped[str | None] = mapped_column(String, nullable=True)
    cmetadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Back-reference
    collection: Mapped[PgCollection | None] = relationship(
        "PgCollection",
        back_populates="embeddings",
    )

    __table_args__ = (Index("ix_cmetadata_gin", cmetadata, postgresql_using="gin"),)

    def __repr__(self) -> str:
        return f"<PgEmbedding id={self.id!r} collection_id={self.collection_id!s}>"
