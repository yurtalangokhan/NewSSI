"""ORM models for providers and user_provider_configs tables."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class ProviderModel(Base):
    """URL-based and API-key-based providers (shared catalog)."""

    __tablename__ = "providers"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_kind: Mapped[str] = mapped_column(Text, nullable=False, default="url", server_default=text("'url'"))
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("FALSE"))
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    time_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    time_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_providers_type", "provider_type"),
        Index("idx_providers_kind", "provider_kind"),
    )


class UserProviderConfigModel(Base):
    """Per-user configuration for a provider (proxy table)."""

    __tablename__ = "user_provider_configs"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[_uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    api_base: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    time_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    time_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", name="uq_user_provider_config"),
        Index("idx_user_provider_configs_user_id", "user_id"),
    )
