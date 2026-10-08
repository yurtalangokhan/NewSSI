"""Make providers.base_url nullable for api-key/cloud providers.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE providers ALTER COLUMN base_url DROP NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE providers SET base_url = '' WHERE base_url IS NULL")
    op.execute("ALTER TABLE providers ALTER COLUMN base_url SET NOT NULL")
