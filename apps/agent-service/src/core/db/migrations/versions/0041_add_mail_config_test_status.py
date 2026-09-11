"""Add last_test_status and last_test_error to mail_config table.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    table_columns = {column["name"] for column in inspector.get_columns("mail_config")}

    if "last_test_status" not in table_columns:
        op.add_column(
            "mail_config",
            sa.Column(
                "last_test_status",
                sa.String(length=20),
                nullable=True,
            ),
        )
    if "last_test_error" not in table_columns:
        op.add_column(
            "mail_config",
            sa.Column(
                "last_test_error",
                sa.Text(),
                nullable=True,
            ),
        )

    op.execute("""
        UPDATE mail_config
        SET last_test_status = 'success'
        WHERE last_tested_at IS NOT NULL AND last_test_status IS NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE mail_config DROP COLUMN IF EXISTS last_test_error")
    op.execute("ALTER TABLE mail_config DROP COLUMN IF EXISTS last_test_status")
