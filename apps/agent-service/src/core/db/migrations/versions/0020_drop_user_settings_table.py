"""Drop user_settings table — all user settings are now managed by user-service.

The user_settings table in the agent_service database is dead code:
- The ORM model (UserSettingsModel) was removed
- No controller, service, or route references it
- All user settings flow through user-service via UserServiceClient HTTP calls
- Migration 0009 created it, 0010 and 0013 added columns

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_settings CASCADE")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            TEXT NOT NULL,
            theme_preference   TEXT,
            chat_background    TEXT,
            default_model      TEXT,
            default_provider_id TEXT,
            auto_scroll        BOOLEAN NOT NULL DEFAULT TRUE,
            shortcut_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
            default_app_mode   TEXT NOT NULL DEFAULT 'AUTO',
            memories           JSONB NOT NULL DEFAULT '[]'::jsonb,
            use_memories       BOOLEAN NOT NULL DEFAULT FALSE,
            enable_memory_tool BOOLEAN NOT NULL DEFAULT FALSE,
            user_preferences   TEXT NOT NULL DEFAULT '',
            prompt_shortcuts   JSONB NOT NULL DEFAULT '[]'::jsonb,
            time_created       TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_settings_user_id UNIQUE (user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings (user_id)"
    )
