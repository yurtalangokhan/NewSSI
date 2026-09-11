"""Add prompt_shortcuts to user_settings.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS prompt_shortcuts JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute("DROP TABLE IF EXISTS input_prompt")


def downgrade() -> None:
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS prompt_shortcuts")
