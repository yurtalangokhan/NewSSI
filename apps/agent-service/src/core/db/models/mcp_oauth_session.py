"""ORM model for the short-lived ``mcp_oauth_session`` table (PKCE / state)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class MCPOAuthSessionModel(Base):
    """One in-flight OAuth authorization. Rows expire after ~10 minutes."""

    __tablename__ = "mcp_oauth_session"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    return_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_url: Mapped[str] = mapped_column(String(500), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("idx_mcp_oauth_session_expires_at", "expires_at"),)

    def __repr__(self) -> str:
        return f"<MCPOAuthSession state={self.state!r} provider_id={self.provider_id}>"
