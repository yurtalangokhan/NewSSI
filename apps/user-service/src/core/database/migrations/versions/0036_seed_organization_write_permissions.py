"""Seed organization write permissions and grant to access-manager.

Migration 0021 seeded only org:list and org:read. The remaining org
management permissions (create, update, delete, move, manage-users)
were never migrated, causing 403 errors when creating or modifying
organizations.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-03
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_PERMISSIONS = [
    ("org:create", "Create Organization", "Create new organization", "create"),
    ("org:update", "Update Organization", "Update organization details", "update"),
    ("org:delete", "Delete Organization", "Delete organizations", "delete"),
    ("org:move", "Move Organization", "Move organizations in hierarchy", "move"),
    (
        "org:manage-users",
        "Manage Organization Users",
        "Manage users in organizations",
        "manage-users",
    ),
]

_PERM_NAMES = [p[0] for p in _NEW_PERMISSIONS]

_PERM_NAMES_JSON = json.dumps(sorted(_PERM_NAMES))


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return bool(inspector.has_table(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _grant_jsonb_permissions(table_name: str, role_name: str, permissions_json: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET permissions = (
                SELECT jsonb_agg(permission ORDER BY permission)
                FROM (
                    SELECT DISTINCT jsonb_array_elements_text(
                        COALESCE(permissions, '[]'::jsonb) || CAST(:permissions_json AS jsonb)
                    ) AS permission
                ) AS merged_permissions
            )
            WHERE name = :role_name
            """
        ).bindparams(role_name=role_name, permissions_json=permissions_json)
    )


def _revoke_jsonb_permissions(table_name: str, role_name: str, permissions: list[str]) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET permissions = COALESCE(
                (
                    SELECT jsonb_agg(permission ORDER BY permission)
                    FROM jsonb_array_elements_text(COALESCE(permissions, '[]'::jsonb)) AS permission
                    WHERE permission != ALL(CAST(:permissions AS text[]))
                ),
                '[]'::jsonb
            )
            WHERE name = :role_name
            """
        ).bindparams(role_name=role_name, permissions=permissions)
    )


def _grant_normalized_permissions(role_name: str, permissions_json: str) -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_name, permission_name)
            SELECT :role_name, permission_name
            FROM jsonb_array_elements_text(CAST(:permissions_json AS jsonb))
                AS permissions(permission_name)
            ON CONFLICT DO NOTHING
            """
        ).bindparams(role_name=role_name, permissions_json=permissions_json)
    )


def _revoke_normalized_permissions(role_name: str, permissions: list[str]) -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE role_name = :role_name
              AND permission_name = ANY(CAST(:permissions AS text[]))
            """
        ).bindparams(role_name=role_name, permissions=permissions)
    )


def upgrade() -> None:
    # 1. Seed the permission catalog entries.
    values = ", ".join(
        f"('{name}', '{label}', '{desc}', 'organization', 'user-service', '{action}', true)"
        for name, label, desc, action in _NEW_PERMISSIONS
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO permissions
                (name, label, description, entity, service, action, is_system)
            VALUES {values}
            ON CONFLICT (name) DO NOTHING
            """
        )
    )

    # 2. Grant to both legacy JSONB columns and the normalized permission table
    #    when either schema shape is present.
    if _has_column("roles", "permissions"):
        _grant_jsonb_permissions("roles", "access-manager", _PERM_NAMES_JSON)
    if _has_column("composite_roles", "permissions"):
        _grant_jsonb_permissions("composite_roles", "enterprise-admin", _PERM_NAMES_JSON)
    if _has_table("role_permissions"):
        _grant_normalized_permissions("access-manager", _PERM_NAMES_JSON)
        _grant_normalized_permissions("enterprise-admin", _PERM_NAMES_JSON)


def downgrade() -> None:
    if _has_column("roles", "permissions"):
        _revoke_jsonb_permissions("roles", "access-manager", _PERM_NAMES)
    if _has_column("composite_roles", "permissions"):
        _revoke_jsonb_permissions("composite_roles", "enterprise-admin", _PERM_NAMES)
    if _has_table("role_permissions"):
        _revoke_normalized_permissions("access-manager", _PERM_NAMES)
        _revoke_normalized_permissions("enterprise-admin", _PERM_NAMES)

    # Remove from permission catalog.
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE name = ANY(CAST(:permissions AS text[]))
            """
        ).bindparams(permissions=_PERM_NAMES)
    )
