"""Grant persona write permissions to agent-workspace-manager and enterprise-admin.

The agent creation UI (``/app/agents/create``) posts to ``POST /api/persona``,
which is gated on ``persona:create`` (see
``apps/agent-service/src/api/routes/PersonaRoute.py``). The
``agent-workspace-manager`` feature bundle seeded by migration 0010 only ever
carried ``persona:read`` even though its description promises operational
management of personas, so ``enterprise-admin`` -- which resolves its agent
permissions solely through that bundle (migration 0029) -- could list personas
but never create, update or delete one, and every create attempt failed with
``auth.forbidden: Gerekli izin eksik: persona:create``.

Grants the three missing write permissions to the bundle and, mirroring
migration 0037, to the ``enterprise-admin`` composite role directly so both the
legacy JSONB columns and the normalized ``role_permissions`` table introduced by
migration 0040 stay consistent.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-04
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMS = ["persona:create", "persona:delete", "persona:update"]
_PERMS_JSON = json.dumps(_PERMS)

_FEATURE_BUNDLE = "agent-workspace-manager"
_COMPOSITE_ROLE = "enterprise-admin"


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
    # Only permissions present in the catalog are inserted: role_permissions
    # has an FK to permissions(name), so an unknown name would abort the
    # migration instead of being skipped.
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_name, permission_name)
            SELECT :role_name, wanted.permission_name
            FROM jsonb_array_elements_text(CAST(:permissions_json AS jsonb))
                AS wanted(permission_name)
            WHERE EXISTS (
                SELECT 1 FROM permissions WHERE permissions.name = wanted.permission_name
            )
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
        _grant_jsonb_permissions("roles", _FEATURE_BUNDLE, _PERMS_JSON)
    if _has_column("composite_roles", "permissions"):
        _grant_jsonb_permissions("composite_roles", _COMPOSITE_ROLE, _PERMS_JSON)
    if _has_table("role_permissions"):
        _grant_normalized_permissions(_FEATURE_BUNDLE, _PERMS_JSON)
        _grant_normalized_permissions(_COMPOSITE_ROLE, _PERMS_JSON)


def downgrade() -> None:
    if _has_column("roles", "permissions"):
        _revoke_jsonb_permissions("roles", _FEATURE_BUNDLE, _PERMS)
    if _has_column("composite_roles", "permissions"):
        _revoke_jsonb_permissions("composite_roles", _COMPOSITE_ROLE, _PERMS)
    if _has_table("role_permissions"):
        _revoke_normalized_permissions(_FEATURE_BUNDLE, _PERMS)
        _revoke_normalized_permissions(_COMPOSITE_ROLE, _PERMS)
