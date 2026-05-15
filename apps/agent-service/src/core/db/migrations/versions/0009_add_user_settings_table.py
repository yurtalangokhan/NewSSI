"""Add user_settings table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            TEXT NOT NULL,
            theme_preference   TEXT,
            chat_background    TEXT,
            default_model      TEXT,
            auto_scroll        BOOLEAN NOT NULL DEFAULT TRUE,
            shortcut_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
            default_app_mode   TEXT NOT NULL DEFAULT 'AUTO',
            memories           JSONB NOT NULL DEFAULT '[]'::jsonb,
            use_memories       BOOLEAN NOT NULL DEFAULT FALSE,
            enable_memory_tool BOOLEAN NOT NULL DEFAULT FALSE,
            user_preferences   TEXT NOT NULL DEFAULT '',
            time_created       TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_settings_user_id UNIQUE (user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_settings")
