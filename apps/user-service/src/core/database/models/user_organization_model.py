"""User-Organization relationship model (many-to-many with role)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserOrganizationModel(Base):
    """
    Many-to-many relationship between users and organizations.

    Users can belong to multiple organizations with different roles.
    """

    __tablename__ = "user_organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Role within this organization
    role_in_org: Mapped[str] = mapped_column(
        String(100), nullable=False, default="member", index=True
    )
    # Roles: "unit_manager", "member", "viewer"

    # Flags
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel", back_populates="user_organizations", lazy="selectin"
    )
    organization: Mapped["OrganizationModel"] = relationship(
        "OrganizationModel", back_populates="user_organizations", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_user_org_unique", "user_id", "organization_id", unique=True),
        Index("idx_user_org_role", "user_id", "organization_id", "role_in_org"),
    )
