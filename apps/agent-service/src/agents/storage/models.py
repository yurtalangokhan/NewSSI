"""Database models for agent storage."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class AgentDefinitionModel(Base):
    """
    Agent definition - stores full agent configuration including graph schema,
    brain type, memory type, tools, sub-agents, pipeline stages, etc.

    Replaces the old class_path-based approach with a structured configuration model.
    """

    __tablename__ = "agent_definitions"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    persona_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, default="dynamic")
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Graph Schema - selects the execution pattern
    graph_schema: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="zero_shot",
    )

    # Brain Type - LLM processing approach
    brain_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="llm",
    )

    # Memory Type - how agent stores context
    memory_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="none",
    )

    # Core configuration
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)

    # Tools configuration - list of MCP tool names
    mcp_tools: Mapped[list] = mapped_column(JSONB, default=list)

    # Per-tool config references. Must not contain secrets.
    mcp_tool_configs: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Knowledge collection binding used by retrieval tools
    rag_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Sub-agents for supervisor/pipeline schemas (JSON array of dicts)
    sub_agents: Mapped[list] = mapped_column(JSONB, default=list)

    # Sub-agent IDs for referencing existing agents (for composition)
    # NEW: Allows agents to reference other agents instead of inlining configs
    sub_agent_ids: Mapped[list] = mapped_column(JSONB, default=list)

    # Version counter for cache validation
    sub_agent_config_version: Mapped[int] = mapped_column(Integer, default=0)

    # Supervisor prompt for supervisor schema
    supervisor_prompt: Mapped[str] = mapped_column(Text, nullable=True)

    # Pipeline stages (JSON array of dicts)
    stages: Mapped[list] = mapped_column(JSONB, default=list)

    # Pipeline prompt for pipeline schema
    pipeline_prompt: Mapped[str] = mapped_column(Text, nullable=True)

    # Self-reflect configuration
    reflection_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    max_iterations: Mapped[int] = mapped_column(Integer, default=3)

    # Metadata
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    tags: Mapped[list] = mapped_column(JSONB, default=list)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_agent_definitions_persona_id", "persona_id"),
        Index("ix_agent_definitions_type", "agent_type"),
        Index("ix_agent_definitions_graph_schema", "graph_schema"),
        Index("ix_agent_definitions_active", "is_active"),
        Index("ix_agent_definitions_name", "name"),
        Index(
            "ix_agent_definitions_sub_agent_ids",
            "sub_agent_ids",
            postgresql_using="gin",
        ),
    )

    def to_config(self) -> dict[str, Any]:
        """Return a config dict suitable for DynamicAgent constructor."""
        return {
            "name": self.name,
            "agent_type": self.agent_type,
            "graph_schema": self.graph_schema,
            "brain_type": self.brain_type,
            "memory_type": self.memory_type,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "mcp_tools": self.mcp_tools or [],
            "mcp_tool_configs": self.mcp_tool_configs or {},
            "rag_config": self.rag_config or {},
            "sub_agents": self.sub_agents or [],
            "sub_agent_ids": self.sub_agent_ids or [],
            "sub_agent_config_version": self.sub_agent_config_version or 0,
            "supervisor_prompt": self.supervisor_prompt,
            "stages": self.stages or [],
            "pipeline_prompt": self.pipeline_prompt,
            "reflection_prompt": self.reflection_prompt,
            "max_iterations": self.max_iterations or 3,
        }
