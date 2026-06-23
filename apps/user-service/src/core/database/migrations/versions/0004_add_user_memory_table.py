"""add user_memory table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("user_memory"):
        op.create_table(
            "user_memory",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(20), nullable=False, server_default="'manual'"),
            sa.Column(
                "time_created",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "time_updated",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    indexes = {index["name"] for index in inspector.get_indexes("user_memory")}
    if "ix_user_memory_user_id" not in indexes:
        op.create_index("ix_user_memory_user_id", "user_memory", ["user_id"])
    if "idx_user_memory_user_time" not in indexes:
        op.create_index(
            "idx_user_memory_user_time",
            "user_memory",
            ["user_id", "time_created"],
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_memory_user_content_lower "
        "ON user_memory (user_id, lower(content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_memory_user_content_lower")
    op.drop_index("idx_user_memory_user_time", table_name="user_memory")
    op.drop_index("ix_user_memory_user_id", table_name="user_memory")
    op.drop_table("user_memory")
