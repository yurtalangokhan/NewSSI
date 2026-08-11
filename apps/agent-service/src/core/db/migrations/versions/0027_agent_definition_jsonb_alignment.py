"""Align agent definition JSON columns with JSONB model types.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_definitions
        ALTER COLUMN mcp_tool_configs
        TYPE JSONB
        USING mcp_tool_configs::jsonb
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE agent_definitions
        ALTER COLUMN mcp_tool_configs
        TYPE JSON
        USING mcp_tool_configs::json
    """)
