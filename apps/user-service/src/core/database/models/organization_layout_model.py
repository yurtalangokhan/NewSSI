"""Persisted shared canvas positions for organizations."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrganizationLayoutModel(Base):
    """One shared visual position for one organization."""

    __tablename__ = "organization_layouts"
    __table_args__ = (
        CheckConstraint(
            "position_x >= -1000000 AND position_x <= 1000000",
            name="ck_organization_layouts_position_x_bounds",
        ),
        CheckConstraint(
            "position_y >= -1000000 AND position_y <= 1000000",
            name="ck_organization_layouts_position_y_bounds",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position_x: Mapped[float] = mapped_column(Float, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
