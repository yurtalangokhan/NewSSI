"""Restore organization read permissions for enterprise administrators.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = (
                SELECT jsonb_agg(permission ORDER BY permission)
                FROM (
                    SELECT DISTINCT jsonb_array_elements_text(
                        permissions || '["org:list", "org:read"]'::jsonb
                    ) AS permission
                ) AS merged_permissions
            )
            WHERE name = 'access-manager'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET permissions = COALESCE(
                (
                    SELECT jsonb_agg(permission ORDER BY permission)
                    FROM jsonb_array_elements_text(permissions) AS permission
                    WHERE permission NOT IN ('org:list', 'org:read')
                ),
                '[]'::jsonb
            )
            WHERE name = 'access-manager'
            """
        )
    )
