"""ORM model for the ``agent_tools`` junction table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class AgentToolsModel(Base):
    """Agent-Tools junction table.

    Links assistants/agents to MCP tools.
    One agent can have multiple tools.
    One tool can be used by multiple agents.
    """

    __tablename__ = "agent_tools"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    agent_id: Mapped[int] = mapped_column(nullable=False)
    tool_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    order_index: Mapped[int] = mapped_column(
        Boolean,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    time_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("idx_agent_tools_agent_id", "agent_id"),
        Index("idx_agent_tools_tool_id", "tool_id"),
    )

    def __repr__(self) -> str:
        return f"<AgentTools agent_id={self.agent_id} tool_id={self.tool_id}>"
