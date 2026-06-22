"""add user personalization settings

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "long_term_memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "extract_memory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column("work_role", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "work_role")
    op.drop_column("user_settings", "extract_memory")
    op.drop_column("user_settings", "long_term_memory_enabled")
