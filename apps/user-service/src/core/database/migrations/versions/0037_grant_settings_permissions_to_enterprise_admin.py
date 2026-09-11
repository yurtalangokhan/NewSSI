"""Grant settings read/update permissions to access-manager and enterprise-admin.

Restores settings:read and settings:update permissions to the access-manager
feature bundle and enterprise-admin composite role, enabling access to
configuration routes such as document processing and mail configuration.

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-04
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMS = ["settings:read", "settings:update"]
_PERMS_JSON = json.dumps(_PERMS)


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
    if _has_column("roles", "permissions"):
        _grant_jsonb_permissions("roles", "access-manager", _PERMS_JSON)
    if _has_column("composite_roles", "permissions"):
        _grant_jsonb_permissions("composite_roles", "enterprise-admin", _PERMS_JSON)
    if _has_table("role_permissions"):
        _grant_normalized_permissions("access-manager", _PERMS_JSON)
        _grant_normalized_permissions("enterprise-admin", _PERMS_JSON)


def downgrade() -> None:
    if _has_column("roles", "permissions"):
        _revoke_jsonb_permissions("roles", "access-manager", _PERMS)
    if _has_column("composite_roles", "permissions"):
        _revoke_jsonb_permissions("composite_roles", "enterprise-admin", _PERMS)
    if _has_table("role_permissions"):
        _revoke_normalized_permissions("access-manager", _PERMS)
        _revoke_normalized_permissions("enterprise-admin", _PERMS)
