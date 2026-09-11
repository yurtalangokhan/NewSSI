"""Persist the SMTP configuration selected by each user.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_mail_credential ADD COLUMN mail_config_id UUID")
    op.execute("""
        DO $$
        DECLARE
            fallback_config_id UUID;
        BEGIN
            SELECT id INTO fallback_config_id
            FROM mail_config
            WHERE is_active IS TRUE
            ORDER BY time_created, id
            LIMIT 1;

            IF EXISTS (SELECT 1 FROM user_mail_credential)
               AND fallback_config_id IS NULL THEN
                RAISE EXCEPTION
                    'Cannot backfill user mail credentials without an active mail config';
            END IF;

            UPDATE user_mail_credential
            SET mail_config_id = fallback_config_id
            WHERE mail_config_id IS NULL;
        END $$
    """)
    op.execute("ALTER TABLE user_mail_credential ALTER COLUMN mail_config_id SET NOT NULL")
    op.execute("""
        ALTER TABLE user_mail_credential
        ADD CONSTRAINT fk_user_mail_credential_mail_config
        FOREIGN KEY (mail_config_id) REFERENCES mail_config(id) ON DELETE RESTRICT
    """)
    op.execute("""
        CREATE INDEX idx_user_mail_credential_mail_config_id
        ON user_mail_credential (mail_config_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_mail_credential_mail_config_id")
    op.execute("""
        ALTER TABLE user_mail_credential
        DROP CONSTRAINT IF EXISTS fk_user_mail_credential_mail_config
    """)
    op.execute("ALTER TABLE user_mail_credential DROP COLUMN mail_config_id")
