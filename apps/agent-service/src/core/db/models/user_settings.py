"""ORM model for per-user UI and chat preference settings."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class UserSettingsModel(Base):
    """Stores frontend user preferences keyed by Keycloak user id (sub)."""

    __tablename__ = "user_settings"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)

    theme_preference: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_background: Mapped[str | None] = mapped_column(Text, nullable=True)

    default_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_scroll: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    shortcut_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    default_app_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="AUTO", server_default=text("'AUTO'")
    )

    long_term_memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )
    extract_memory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    user_preferences: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    prompt_shortcuts: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    time_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_settings_user_id"),
        Index("idx_user_settings_user_id", "user_id"),
    )
