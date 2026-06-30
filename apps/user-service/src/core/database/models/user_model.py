import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
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
    keycloak_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
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
