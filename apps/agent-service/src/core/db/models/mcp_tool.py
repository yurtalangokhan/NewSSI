"""ORM model for the ``mcp_tool`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class MCPToolModel(Base):
    """MCP Tool - cached tool definition from MCP provider.

    Tools are fetched from MCP providers and cached locally for quick access.
    Each tool has a name, description, and input schema.
    """

    __tablename__ = "mcp_tool"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    provider_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="",
        server_default=text("''"),
    )
    input_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    tool_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    last_synced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("idx_mcp_tool_provider_id", "provider_id"),
        Index("idx_mcp_tool_name", "name"),
        Index("idx_mcp_tool_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<MCPTool id={self.id} name={self.name!r} provider_id={self.provider_id}>"
