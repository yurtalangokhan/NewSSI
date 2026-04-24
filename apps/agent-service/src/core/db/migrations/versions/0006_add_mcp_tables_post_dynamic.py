"""Add MCP provider, tool, and agent_tools tables after dynamic-agent migrations.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24

This migration intentionally re-introduces MCP table creation in a linear chain
so Alembic history is deterministic (no duplicate revision IDs).
All statements are IF NOT EXISTS to keep existing databases safe.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # mcp_provider
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_provider (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name          VARCHAR(255) NOT NULL UNIQUE,
            type          VARCHAR(50) NOT NULL DEFAULT 'external',
            url           VARCHAR(500),
            transport     VARCHAR(50) NOT NULL DEFAULT 'streamable_http',
            config        JSONB DEFAULT '{}'::jsonb,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            is_builtin    BOOLEAN NOT NULL DEFAULT FALSE,
            description   TEXT DEFAULT ''::text,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_provider_type ON mcp_provider(type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_provider_is_active ON mcp_provider(is_active)")

    # ------------------------------------------------------------------
    # mcp_tool
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_tool (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider_id    UUID NOT NULL,
            name           VARCHAR(255) NOT NULL,
            description    TEXT DEFAULT ''::text,
            input_schema   JSONB DEFAULT '{}'::jsonb,
            output_schema  JSONB DEFAULT '{}'::jsonb,
            metadata       JSONB DEFAULT '{}'::jsonb,
            category       VARCHAR(100),
            tags           JSONB DEFAULT '[]'::jsonb,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            last_synced    TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tool_provider_id ON mcp_tool(provider_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tool_name ON mcp_tool(name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mcp_tool_category ON mcp_tool(category)")

    # ------------------------------------------------------------------
    # agent_tools
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_tools (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id     INTEGER NOT NULL,
            tool_id      UUID NOT NULL,
            config       JSONB DEFAULT '{}'::jsonb,
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            order_index  INTEGER NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_tools_agent_id ON agent_tools(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_tools_tool_id ON agent_tools(tool_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_tools")
    op.execute("DROP TABLE IF EXISTS mcp_tool")
    op.execute("DROP TABLE IF EXISTS mcp_provider")
