"""ORM model for the ``persona`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class PersonaModel(Base):
    """Persona/agent model for custom AI agents.

    Personas can be either:
    - Built-in agents (is_builtin=True, builtin_key references agents.py keys)
    - Custom user-created agents (is_builtin=False)
    """

    __tablename__ = "persona"

    id: Mapped[int | None] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
    task_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default=text("''"),
    )
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
    # For custom agents: which base agent to use (chatbot, configurable-mcp-agent, etc.)
    base_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For custom agents: list of MCP tool names to bind
    mcp_tools: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Per-tool configuration references. Must not contain secrets.
    mcp_tool_configs: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # Long-term memory toggle for this persona/agent
    long_term_memory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("FALSE"),
    )
    # RAG configuration: {"document_processing": [...uuids], "knowledge_graph": [...uuids]}
    rag_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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
        Index("idx_persona_user_id", "user_id"),
        Index(
            "idx_persona_builtin",
            "is_builtin",
            postgresql_where=text("is_builtin = TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Persona id={self.id} name={self.name!r} builtin={self.is_builtin}>"
