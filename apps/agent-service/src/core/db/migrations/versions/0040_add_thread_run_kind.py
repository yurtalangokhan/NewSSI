"""Add run_kind column to thread table.

Tracks the execution namespace of a conversation thread: "production" (default)
vs "playground" (canvas test runs).

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    thread_columns = {column["name"] for column in inspector.get_columns("thread")}

    if "run_kind" not in thread_columns:
        op.add_column(
            "thread",
            sa.Column(
                "run_kind",
                sa.String(length=32),
                nullable=False,
                server_default="production",
            ),
        )

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_thread_run_kind
        ON thread (run_kind)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_thread_run_kind")
    op.execute("ALTER TABLE thread DROP COLUMN IF EXISTS run_kind")
