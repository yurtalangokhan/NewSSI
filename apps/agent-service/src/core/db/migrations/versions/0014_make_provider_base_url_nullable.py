"""Make providers.base_url nullable for api-key/cloud providers.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE providers ALTER COLUMN base_url DROP NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE providers SET base_url = '' WHERE base_url IS NULL")
    op.execute("ALTER TABLE providers ALTER COLUMN base_url SET NOT NULL")
