"""ORM model for the unified ``agents`` table."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class AgentModel(Base):
    """Unified agent record for personas, assistants, and dynamic agents."""

    __tablename__ = "agents"

    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid.uuid4,
    )
    legacy_persona_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    legacy_assistant_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    legacy_definition_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="dynamic",
        server_default=text("'dynamic'"),
    )
    graph_schema: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="zero_shot",
        server_default=text("'zero_shot'"),
    )
    brain_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="llm",
        server_default=text("'llm'"),
    )
    memory_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="none",
        server_default=text("'none'"),
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    datetime_aware: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    llm_model_provider_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model_version_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    starter_messages: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rag_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    mcp_tools: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    mcp_tool_configs: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    sub_agents: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    sub_agent_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    sub_agent_config_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    supervisor_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    stages: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    pipeline_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_iterations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )
    version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
        server_default=text("'1.0.0'"),
    )
    tags: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    user_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="dev-user",
        server_default=text("'dev-user'"),
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    builtin_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("TRUE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_agents_type", "agent_type"),
        Index("ix_agents_user_id", "user_id"),
        Index("ix_agents_active", "is_active"),
        Index("ix_agents_name", "name"),
        Index("ix_agents_legacy_persona_id", "legacy_persona_id"),
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id!s} name={self.name!r} type={self.agent_type!r}>"
