import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserRole(str, enum.Enum):
    ENDUSER = "enduser"
    ADMIN = "admin"


_LEGACY_ROLE_MAP = {
    "ADMIN": UserRole.ADMIN.value,
    "admin": UserRole.ADMIN.value,
    "ENDUSER": UserRole.ENDUSER.value,
    "enduser": UserRole.ENDUSER.value,
    "BASIC": UserRole.ENDUSER.value,
    "basic": UserRole.ENDUSER.value,
    "LIMITED": UserRole.ENDUSER.value,
    "limited": UserRole.ENDUSER.value,
    "CURATOR": UserRole.ENDUSER.value,
    "curator": UserRole.ENDUSER.value,
    "GLOBAL_CURATOR": UserRole.ENDUSER.value,
    "global_curator": UserRole.ENDUSER.value,
    "EXT_PERM_USER": UserRole.ENDUSER.value,
    "ext_perm_user": UserRole.ENDUSER.value,
    "SLACK_USER": UserRole.ENDUSER.value,
    "slack_user": UserRole.ENDUSER.value,
}


def normalize_user_role(role: object | None) -> str:
    if isinstance(role, UserRole):
        return role.value
    raw_role = str(role or UserRole.ENDUSER.value)
    if raw_role.startswith("UserRole."):
        raw_role = raw_role.rsplit(".", 1)[-1]
    return _LEGACY_ROLE_MAP.get(raw_role, UserRole.ENDUSER.value)


def is_admin_role(role: object | None) -> bool:
    return normalize_user_role(role) == UserRole.ADMIN.value


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
    role: Mapped[str] = mapped_column(String(50), default=UserRole.ENDUSER.value, nullable=False)
    invited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel", back_populates="user", lazy="selectin"
    )
    audit_logs: Mapped[list["AuditLogModel"]] = relationship(
        "AuditLogModel", back_populates="user", lazy="selectin"
    )
