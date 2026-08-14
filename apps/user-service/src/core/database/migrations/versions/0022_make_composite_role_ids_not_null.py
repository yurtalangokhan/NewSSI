"""make composite role_ids not null

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE composite_roles SET role_ids = '[]'::jsonb WHERE role_ids IS NULL")
    op.alter_column(
        "composite_roles",
        "role_ids",
        existing_type=JSONB,
        nullable=False,
        server_default="[]",
    )


def downgrade() -> None:
    op.alter_column(
        "composite_roles",
        "role_ids",
        existing_type=JSONB,
        nullable=True,
        existing_server_default=sa.text("'[]'::jsonb"),
    )
