"""Normalize role permission and hierarchy tables.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return bool(inspector.has_table(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_name VARCHAR(100) NOT NULL,
            permission_name VARCHAR(100) NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
            PRIMARY KEY (role_name, permission_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS role_hierarchy (
            parent_role VARCHAR(100) NOT NULL REFERENCES composite_roles(name) ON DELETE CASCADE,
            child_role VARCHAR(100) NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
            PRIMARY KEY (parent_role, child_role)
        )
        """
    )
    if _has_column("roles", "permissions"):
        op.execute(
            """
            INSERT INTO role_permissions (role_name, permission_name)
            SELECT roles.name, permissions.value::text
            FROM roles
            CROSS JOIN LATERAL jsonb_array_elements_text(roles.permissions) AS permissions(value)
            ON CONFLICT DO NOTHING
            """
        )
    if _has_column("composite_roles", "permissions"):
        op.execute(
            """
            INSERT INTO role_permissions (role_name, permission_name)
            SELECT composite_roles.name, permissions.value::text
            FROM composite_roles
            CROSS JOIN LATERAL jsonb_array_elements_text(composite_roles.permissions)
                AS permissions(value)
            ON CONFLICT DO NOTHING
            """
        )
    if _has_column("composite_roles", "role_ids"):
        op.execute(
            """
            INSERT INTO role_hierarchy (parent_role, child_role)
            SELECT composite_roles.name, child_roles.value::text
            FROM composite_roles
            CROSS JOIN LATERAL jsonb_array_elements_text(composite_roles.role_ids)
                AS child_roles(value)
            WHERE EXISTS (SELECT 1 FROM roles WHERE roles.name = child_roles.value::text)
            ON CONFLICT DO NOTHING
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS role_hierarchy")
    op.execute("DROP TABLE IF EXISTS role_permissions")
