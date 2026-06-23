"""add external Keycloak user flag

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "is_external_keycloak_user" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "is_external_keycloak_user",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("users")}
    if "is_external_keycloak_user" in columns:
        op.drop_column("users", "is_external_keycloak_user")
