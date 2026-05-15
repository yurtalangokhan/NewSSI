import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class UserSettingsModel(Base):
    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    theme_preference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chat_background: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auto_scroll: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    shortcut_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_app_mode: Mapped[str] = mapped_column(String(20), default="AUTO", nullable=False)
    memories: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    use_memories: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enable_memory_tool: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prompt_shortcuts: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    time_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    time_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="settings")
