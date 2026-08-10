"""Permission audit log model for tracking permission changes."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PermissionAuditModel(Base):
    """Audit log for permission changes (grant, revoke, update)."""

    __tablename__ = "permission_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Action
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # "grant", "revoke", "update"

    # Permission details
    permission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Target (organization or user)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # "organization" or "user"
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Permission level
    permission_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_permission_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Actor
    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True
    )

    # Metadata
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
