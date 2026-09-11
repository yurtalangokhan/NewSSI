"""Repair role identities omitted from the normalized role catalog.

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return bool(inspector.has_table(table_name))


def _columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    if not _has_table(inspector, table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, "roles") or not _has_table(inspector, "composite_roles"):
        return

    role_columns = _columns(inspector, "roles")
    if "permissions" in role_columns:
        op.execute(
            """
            INSERT INTO roles (name, description, service_client, permissions, created_at)
            SELECT name, description, 'user-service', permissions, created_at
            FROM composite_roles
            ON CONFLICT (name) DO NOTHING
            """
        )
    else:
        op.execute(
            """
            INSERT INTO roles (name, description, service_client, created_at)
            SELECT name, description, 'user-service', created_at
            FROM composite_roles
            ON CONFLICT (name) DO NOTHING
            """
        )

    composite_columns = _columns(inspector, "composite_roles")
    if _has_table(inspector, "role_permissions") and "permissions" in composite_columns:
        op.execute(
            """
            INSERT INTO role_permissions (role_name, permission_name)
            SELECT composite_roles.name, permission.value::text
            FROM composite_roles
            CROSS JOIN LATERAL jsonb_array_elements_text(composite_roles.permissions)
                AS permission(value)
            WHERE EXISTS (
                SELECT 1 FROM permissions WHERE permissions.name = permission.value::text
            )
            ON CONFLICT DO NOTHING
            """
        )

    if _has_table(inspector, "role_hierarchy") and "role_ids" in composite_columns:
        op.execute(
            """
            INSERT INTO role_hierarchy (parent_role, child_role)
            SELECT composite_roles.name, child_role.value::text
            FROM composite_roles
            CROSS JOIN LATERAL jsonb_array_elements_text(composite_roles.role_ids)
                AS child_role(value)
            WHERE EXISTS (SELECT 1 FROM roles WHERE roles.name = child_role.value::text)
            ON CONFLICT DO NOTHING
            """
        )


def downgrade() -> None:
    """Keep repaired role identities to avoid revoking user access."""
