"""repair system settings and role columns

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("system_settings"):
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=120), nullable=False),
            sa.Column("value", JSONB, nullable=False, server_default="{}"),
            sa.PrimaryKeyConstraint("key"),
        )
    else:
        system_columns = _columns("system_settings")
        if "key" not in system_columns:
            op.add_column("system_settings", sa.Column("key", sa.String(length=120)))
        if "value" not in system_columns:
            op.add_column(
                "system_settings",
                sa.Column("value", JSONB, nullable=False, server_default="{}"),
            )

    role_columns = _columns("roles")
    if role_columns:
        if "created_at" not in role_columns:
            op.add_column(
                "roles",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )
        if "permissions" not in role_columns:
            op.add_column(
                "roles",
                sa.Column("permissions", JSONB, nullable=False, server_default="[]"),
            )

    composite_columns = _columns("composite_roles")
    if composite_columns:
        if "role_ids" not in composite_columns and "coarse_roles" in composite_columns:
            op.alter_column("composite_roles", "coarse_roles", new_column_name="role_ids")
            composite_columns.remove("coarse_roles")
            composite_columns.add("role_ids")
        if "role_ids" not in composite_columns:
            op.add_column(
                "composite_roles",
                sa.Column("role_ids", JSONB, nullable=False, server_default="[]"),
            )
        if "is_admin" not in composite_columns:
            op.add_column(
                "composite_roles",
                sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
            )
            op.execute(
                "UPDATE composite_roles SET is_admin = true "
                "WHERE name IN ('system-admin', 'enterprise-admin')"
            )
        if "created_at" not in composite_columns:
            op.add_column(
                "composite_roles",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )


def downgrade() -> None:
    # Repair migration is intentionally not destructive.
    pass
