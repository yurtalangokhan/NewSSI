"""add base_agent and mcp_tools columns to persona table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-10

Adds the two columns that were introduced in the ORM model but may be
missing when the persona table was created before migration 0002 was
applied (or when 0002 was skipped because the table already existed).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE persona
            ADD COLUMN IF NOT EXISTS base_agent TEXT,
            ADD COLUMN IF NOT EXISTS mcp_tools   JSONB
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS base_agent")
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS mcp_tools")
