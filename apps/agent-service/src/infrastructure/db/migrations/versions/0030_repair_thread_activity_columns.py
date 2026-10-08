"""Repair missing thread activity columns after rebased revision graph.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-14

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE thread ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ")
    op.execute("UPDATE thread SET last_message_at = updated_at WHERE last_message_at IS NULL")
    op.execute("ALTER TABLE thread ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_thread_activity_order
        ON thread ((COALESCE(last_message_at, created_at)) DESC, thread_id DESC)
        """
    )


def downgrade() -> None:
    """Repair migrations are intentionally non-destructive."""
