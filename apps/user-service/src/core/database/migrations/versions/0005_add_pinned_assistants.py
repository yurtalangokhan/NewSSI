"""add pinned_assistants column to user_settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("user_settings")}
    if "pinned_assistants" not in columns:
        op.add_column(
            "user_settings",
            sa.Column(
                "pinned_assistants",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("user_settings", "pinned_assistants")
