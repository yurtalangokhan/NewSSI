"""repair feature bundle permissions

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_PERMISSION_RULES: tuple[tuple[str, str], ...] = (
    (
        "access-admin",
        "(service = 'user-service' OR service = 'system')",
    ),
    (
        "agent-workspace-admin",
        "(service = 'agent-service' AND feature IN ('agents', 'chat', 'workspace'))",
    ),
    (
        "knowledge-admin",
        "(service = 'rag-service')",
    ),
    (
        "tooling-admin",
        "((service = 'agent-service' AND feature = 'tools') OR service = 'tools-service')",
    ),
)


def _repair_role_permissions(role_name: str, where_clause: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE roles
            SET permissions = COALESCE(
                (
                    SELECT jsonb_agg(name ORDER BY name)
                    FROM permissions
                    WHERE {where_clause}
                ),
                '[]'::jsonb
            )
            WHERE name = :role_name
            """
        ).bindparams(role_name=role_name)
    )


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE composite_roles
            SET role_ids = COALESCE(
                (
                    SELECT jsonb_agg(role_name ORDER BY role_name)
                    FROM (
                        SELECT value AS role_name
                        FROM jsonb_array_elements_text(role_ids) AS elem(value)
                        WHERE value <> 'platform-admin'
                    ) AS roles
                ),
                '[]'::jsonb
            )
            WHERE role_ids ? 'platform-admin'
            """
        )
    )
    op.execute("DELETE FROM roles WHERE name = 'platform-admin'")

    for role_name, where_clause in ROLE_PERMISSION_RULES:
        _repair_role_permissions(role_name, where_clause)


def downgrade() -> None:
    pass
