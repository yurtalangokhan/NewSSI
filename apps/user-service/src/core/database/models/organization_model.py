"""Organization model for hierarchical organization structure."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OrganizationModel(Base):
    """
    Hierarchical organization/department structure using Materialized Path pattern.

    Supports unlimited nesting depth with fast tree queries.
    Path format: /root_id/parent_id/current_id/
    """

    __tablename__ = "organizations"
    __table_args__ = (
        Index(
            "uq_organizations_single_root",
            text("(parent_id IS NULL)"),
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hierarchical structure (Materialized Path)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    # Example path: "/root_id/parent_id/current_id/"
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Metadata
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    parent: Mapped["OrganizationModel | None"] = relationship(
        "OrganizationModel",
        remote_side="OrganizationModel.id",
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list["OrganizationModel"]] = relationship(
        "OrganizationModel",
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    user_organizations: Mapped[list["UserOrganizationModel"]] = relationship(
        "UserOrganizationModel",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    resource_permissions: Mapped[list["ResourcePermissionModel"]] = relationship(
        "ResourcePermissionModel",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
