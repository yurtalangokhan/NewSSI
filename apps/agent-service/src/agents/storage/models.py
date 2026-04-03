"""Database models for agent storage."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class AgentDefinitionModel(Base):
    """Agent definition - stores agent metadata and configuration."""

    __tablename__ = "agent_definitions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Class path for dynamic loading
    class_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Configuration
    config_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    default_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Metadata
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    tags: Mapped[list] = mapped_column(JSON, default=list)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_agent_definitions_type", "agent_type"),
        Index("ix_agent_definitions_active", "is_active"),
    )


class AgentInstanceModel(Base):
    """Agent instance - runtime state for an agent."""

    __tablename__ = "agent_instances"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Reference to definition
    definition_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # User/tenant association
    user_id: Mapped[str] = mapped_column(String(100), nullable=True)

    # Runtime configuration overrides
    runtime_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Checkpoint/state
    state: Mapped[dict] = mapped_column(JSON, default=dict)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_agent_instances_definition", "definition_id"),
        Index("ix_agent_instances_user", "user_id"),
    )


class SubAgentModel(Base):
    """Sub-agent configuration for manager agents."""

    __tablename__ = "agent_sub_agents"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Parent manager agent
    manager_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Sub-agent config
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    mcp_tools: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(50), nullable=True)

    # Order in team
    order_index: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_sub_agents_manager", "manager_id"),)


class PipelineStageModel(Base):
    """Pipeline stage configuration."""

    __tablename__ = "agent_pipeline_stages"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Parent pipeline agent
    pipeline_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Stage config
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    mcp_tools: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(50), nullable=True)

    # Stage order
    stage_order: Mapped[int] = mapped_column(default=0)

    # Error handling
    on_error: Mapped[str] = mapped_column(String(20), default="abort")
    retry_count: Mapped[int] = mapped_column(default=2)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_pipeline_stages_pipeline", "pipeline_id"),)
