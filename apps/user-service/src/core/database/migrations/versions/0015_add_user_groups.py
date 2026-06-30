"""add external groups to users

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "groups" not in columns:
        op.add_column(
            "users",
            sa.Column("groups", JSONB(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "groups" in columns:
        op.drop_column("users", "groups")
