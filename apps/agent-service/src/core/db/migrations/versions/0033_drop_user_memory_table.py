"""Drop legacy user_memory table from agent-service.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_memory CASCADE")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memory (
            id UUID PRIMARY KEY,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source VARCHAR(50) NOT NULL DEFAULT 'manual',
            time_created TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_memory_user_id "
        "ON user_memory (user_id, time_created DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_memory_user_content_lower "
        "ON user_memory (user_id, lower(content))"
    )
