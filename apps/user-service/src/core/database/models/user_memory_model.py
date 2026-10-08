from datetime import datetime
import uuid

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserMemoryModel(Base):
    __tablename__ = "user_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    #: BCP-47 tag the extractor's model declared for this fact, e.g. "tr",
    #: "zh-Hans". Nullable, and deliberately without a default: rows written
    #: before this column existed, and facts a user typed in by hand, have no
    #: declared language -- and "unknown" is not the same as any particular
    #: language. RFC 5646 tags fit within 35 characters.
    language: Mapped[str | None] = mapped_column(String(35), nullable=True)
    time_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    time_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_user_memory_user_time", "user_id", "time_created"),
        Index("uq_user_memory_user_content_lower", "user_id", func.lower(content), unique=True),
    )
