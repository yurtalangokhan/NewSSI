"""Add rag_config column to agent_definitions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_definitions ADD COLUMN IF NOT EXISTS rag_config JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE agent_definitions DROP COLUMN IF EXISTS rag_config")
