"""grant LLM provider permissions to tooling feature bundles

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-13

"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _add_role_permissions(role_name: str, permissions: tuple[str, ...]) -> None:
    permissions_json = json.dumps(list(permissions))
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = (
                SELECT jsonb_agg(permission ORDER BY permission)
                FROM (
                    SELECT DISTINCT permission
                    FROM (
                        SELECT jsonb_array_elements_text(COALESCE(permissions, '[]'::jsonb))
                            AS permission
                        FROM roles
                        WHERE name = :role_name
                        UNION ALL
                        SELECT jsonb_array_elements_text(CAST(:permissions_json AS jsonb))
                            AS permission
                    ) AS combined
                ) AS distinct_permissions
            )
            WHERE name = :role_name
            """
        ).bindparams(role_name=role_name, permissions_json=permissions_json)
    )


def upgrade() -> None:
    _add_role_permissions(
        "tooling-admin",
        (
            "provider:create",
            "provider:delete",
            "provider:read",
            "provider:update",
        ),
    )
    _add_role_permissions("tooling-user", ("provider:read",))


def downgrade() -> None:
    pass
