"""Add SMTP mail configs and MCP tool config bindings.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mail_config (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(120) NOT NULL,
            host VARCHAR(255) NOT NULL,
            port INTEGER NOT NULL,
            username VARCHAR(255) NOT NULL,
            password_encrypted TEXT NOT NULL,
            from_email VARCHAR(255) NOT NULL,
            from_name VARCHAR(255),
            security VARCHAR(20) NOT NULL DEFAULT 'starttls',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_tested_at TIMESTAMPTZ,
            time_created TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mail_config_user_id ON mail_config (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mail_config_is_active ON mail_config (is_active)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mail_config_user_name ON mail_config (user_id, name)"
    )
    op.execute("""
        ALTER TABLE persona
        ADD COLUMN IF NOT EXISTS mcp_tool_configs JSONB NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute("""
        ALTER TABLE agent_definitions
        ADD COLUMN IF NOT EXISTS mcp_tool_configs JSON NOT NULL DEFAULT '{}'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE agent_definitions DROP COLUMN IF EXISTS mcp_tool_configs")
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS mcp_tool_configs")
    op.execute("DROP INDEX IF EXISTS idx_mail_config_user_name")
    op.execute("DROP INDEX IF EXISTS idx_mail_config_is_active")
    op.execute("DROP INDEX IF EXISTS idx_mail_config_user_id")
    op.execute("DROP TABLE IF EXISTS mail_config")
