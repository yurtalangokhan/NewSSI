"""add is_admin column, migrate admin->system-admin, remove admin role

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("roles")}
    if "is_admin" not in columns:
        op.add_column(
            "roles",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        )

    # Mark system-admin and enterprise-admin as admin roles
    op.execute(
        "UPDATE roles SET is_admin = true WHERE name IN ('system-admin', 'enterprise-admin')"
    )

    # Migrate existing admin users to system-admin
    op.execute("UPDATE users SET role = 'system-admin' WHERE role = 'admin'")

    # Remove the old admin role from roles table
    op.execute("DELETE FROM roles WHERE name = 'admin'")


def downgrade() -> None:
    # Re-insert the admin role
    op.execute(
        """INSERT INTO roles (name, description, permissions, is_builtin, is_admin)
           VALUES ('admin', 'Administrator with full access', '["*"]', true, true)
           ON CONFLICT (name) DO NOTHING"""
    )

    # Revert system-admin users back to admin (if any)
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'system-admin'")

    # Drop is_admin column
    op.drop_column("roles", "is_admin")
