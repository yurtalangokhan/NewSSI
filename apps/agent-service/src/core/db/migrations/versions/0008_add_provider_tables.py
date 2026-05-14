"""Add providers and user_providers tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          TEXT NOT NULL,
            name             TEXT NOT NULL,
            provider_type    TEXT NOT NULL,
            base_url         TEXT NOT NULL,
            api_key_encrypted TEXT,
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            is_builtin       BOOLEAN NOT NULL DEFAULT FALSE,
            config           JSONB DEFAULT '{}'::jsonb,
            time_created     TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, provider_type, base_url)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_providers_user_id ON providers (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_providers_type ON providers (provider_type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_providers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             TEXT NOT NULL,
            name                TEXT NOT NULL,
            provider_type       TEXT NOT NULL,
            api_key_encrypted   TEXT,
            api_key_fingerprint TEXT,
            api_base            TEXT,
            api_version         TEXT,
            deployment_name     TEXT,
            custom_config       JSONB DEFAULT '{}'::jsonb,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            time_created        TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, provider_type, api_key_fingerprint)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_providers_user_id ON user_providers (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_providers_type ON user_providers (provider_type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_providers")
    op.execute("DROP TABLE IF EXISTS providers")
