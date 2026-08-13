"""Resource permission model for granular access control."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ResourcePermissionModel(Base):
    """
    Granular resource-level permissions.

    Supports both organization-level and individual user-level permissions.
    Resource types: agent, agent_group, rag_collection, connector
    """

    __tablename__ = "resource_permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Resource definition
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Permission target (either organization OR user, not both)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Permission level
    permission_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="read", index=True
    )
    # Levels: "owner", "admin", "write", "read", "execute"

    # Metadata
    is_inherited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Inherited from parent organization?

    # Timestamps
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["OrganizationModel | None"] = relationship(
        "OrganizationModel", back_populates="resource_permissions", lazy="selectin"
    )
    user: Mapped["UserModel | None"] = relationship(
        "UserModel", back_populates="resource_permissions", lazy="selectin"
    )

    __table_args__ = (
        # Unique constraint: one permission per resource per organization
        Index(
            "idx_resource_perm_org_unique",
            "resource_type",
            "resource_id",
            "organization_id",
            unique=True,
            postgresql_where=text("organization_id IS NOT NULL"),
        ),
        # Unique constraint: one permission per resource per user
        Index(
            "idx_resource_perm_user_unique",
            "resource_type",
            "resource_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("idx_resource_type_id", "resource_type", "resource_id"),
        # Either organization_id or user_id must be set (not both, not neither)
        CheckConstraint(
            "(organization_id IS NOT NULL AND user_id IS NULL) OR "
            "(organization_id IS NULL AND user_id IS NOT NULL)",
            name="check_exclusive_org_or_user",
        ),
    )
