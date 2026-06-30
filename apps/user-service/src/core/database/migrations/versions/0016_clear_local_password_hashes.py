"""clear local password hashes

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    updates: dict[str, object] = {}
    if "hashed_password" in columns:
        updates["hashed_password"] = None
    if "password_configured" in columns:
        updates["password_configured"] = False
    if updates:
        users = sa.table(
            "users",
            sa.column("hashed_password", sa.String()),
            sa.column("password_configured", sa.Boolean()),
        )
        op.execute(sa.update(users).values(**updates))


def downgrade() -> None:
    pass
