"""ORM model for the ``mcp_provider`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class MCPProviderModel(Base):
    """MCP Provider - external MCP server configuration.

    MCP providers are MCP-compatible servers that expose tools.
    Can be:
    - Builtin: tool-service (automatically registered)
    - External: custom MCP servers (user-configured)
    """

    __tablename__ = "mcp_provider"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="external",
    )
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transport: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="streamable_http",
    )
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="",
        server_default=text("''"),
    )
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    time_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("idx_mcp_provider_type", "type"),
        Index("idx_mcp_provider_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<MCPProvider id={self.id} name={self.name!r} type={self.type}>"
