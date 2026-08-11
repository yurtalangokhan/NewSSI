import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def normalize_user_role(role: object | None) -> str:
    raw_role = str(role or "enduser")
    if raw_role.startswith("UserRole."):
        raw_role = raw_role.rsplit(".", 1)[-1]
    return raw_role


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="enduser", nullable=False)
    groups: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    invited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_external_keycloak_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    settings: Mapped["UserSettingsModel | None"] = relationship(
        "UserSettingsModel", back_populates="user", uselist=False, lazy="selectin"
    )
    api_keys: Mapped[list["ApiKeyModel"]] = relationship(
        "ApiKeyModel", back_populates="user", lazy="selectin"
    )
    audit_logs: Mapped[list["AuditLogModel"]] = relationship(
        "AuditLogModel", back_populates="user", lazy="selectin"
    )
    user_organizations: Mapped[list["UserOrganizationModel"]] = relationship(
        "UserOrganizationModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    resource_permissions: Mapped[list["ResourcePermissionModel"]] = relationship(
        "ResourcePermissionModel",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
        Index("ix_users_keycloak_id", "keycloak_id"),
    )
