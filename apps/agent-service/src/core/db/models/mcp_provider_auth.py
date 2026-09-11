"""ORM model for the ``mcp_provider_auth`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class MCPProviderAuthModel(Base):
    """Per-user or admin/shared credentials + OAuth tokens for an MCP provider.

    ``user_id IS NULL`` denotes the admin/shared credential row. All secret
    columns hold Fernet ciphertext produced by ``core.security.encryption``.
    """

    __tablename__ = "mcp_provider_auth"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mcp_provider.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    oauth_scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    time_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_mcp_provider_auth_provider_id", "provider_id"),
        Index(
            "uq_mcp_provider_auth_admin",
            "provider_id",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
        Index(
            "uq_mcp_provider_auth_user",
            "provider_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<MCPProviderAuth provider_id={self.provider_id} user_id={self.user_id!r}>"
