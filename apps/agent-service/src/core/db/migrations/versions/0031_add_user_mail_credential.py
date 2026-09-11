"""Add user_mail_credential table and make mail_config credentials nullable.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mail_credential (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            username VARCHAR(255) NOT NULL,
            password_encrypted TEXT NOT NULL,
            from_email VARCHAR(255) NOT NULL,
            from_name VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_tested_at TIMESTAMPTZ,
            time_created TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_mail_credential_user_id ON user_mail_credential (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_mail_credential_is_active ON user_mail_credential (is_active)"
    )
    # Make user-specific fields in mail_config nullable for pure SMTP server records
    op.execute("ALTER TABLE mail_config ALTER COLUMN username DROP NOT NULL")
    op.execute("ALTER TABLE mail_config ALTER COLUMN password_encrypted DROP NOT NULL")
    op.execute("ALTER TABLE mail_config ALTER COLUMN from_email DROP NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_mail_credential_is_active")
    op.execute("DROP INDEX IF EXISTS idx_user_mail_credential_user_id")
    op.execute("DROP TABLE IF EXISTS user_mail_credential")
