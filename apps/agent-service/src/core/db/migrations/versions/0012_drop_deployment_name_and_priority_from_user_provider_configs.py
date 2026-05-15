"""Drop deployment_name and priority from user_provider_configs.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_provider_configs_user_priority")
    op.execute("ALTER TABLE user_provider_configs DROP COLUMN IF EXISTS deployment_name")
    op.execute("ALTER TABLE user_provider_configs DROP COLUMN IF EXISTS priority")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_provider_configs_user_id "
        "ON user_provider_configs (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_provider_configs_user_id")
    op.execute(
        "ALTER TABLE user_provider_configs "
        "ADD COLUMN IF NOT EXISTS deployment_name TEXT"
    )
    op.execute(
        "ALTER TABLE user_provider_configs "
        "ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_provider_configs_user_priority "
        "ON user_provider_configs (user_id, priority)"
    )
