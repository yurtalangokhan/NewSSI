"""Add activity and access timestamps to chat session threads.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    thread_columns = {column["name"] for column in inspector.get_columns("thread")}

    if "last_message_at" not in thread_columns:
        op.add_column(
            "thread", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.execute("UPDATE thread SET last_message_at = updated_at WHERE last_message_at IS NULL")

    if "last_accessed_at" not in thread_columns:
        op.add_column(
            "thread", sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_thread_activity_order
        ON thread ((COALESCE(last_message_at, created_at)) DESC, thread_id DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_thread_activity_order")
    op.execute("ALTER TABLE thread DROP COLUMN IF EXISTS last_accessed_at")
    op.execute("ALTER TABLE thread DROP COLUMN IF EXISTS last_message_at")
