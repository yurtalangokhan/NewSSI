"""Add missing foreign key constraints for agent-service tables.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mcp_tool
        ADD CONSTRAINT fk_mcp_tool_provider_id
        FOREIGN KEY (provider_id) REFERENCES mcp_provider(id)
        ON DELETE CASCADE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_tools
        ADD CONSTRAINT fk_agent_tools_tool_id
        FOREIGN KEY (tool_id) REFERENCES mcp_tool(id)
        ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_tools DROP CONSTRAINT IF EXISTS fk_agent_tools_tool_id")
    op.execute("ALTER TABLE mcp_tool DROP CONSTRAINT IF EXISTS fk_mcp_tool_provider_id")
