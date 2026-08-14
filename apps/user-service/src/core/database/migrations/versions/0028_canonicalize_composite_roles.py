"""canonicalize composite roles

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CANONICAL_ROLES = {
    "system-admin": (
        "System administrator",
        '["access-admin", "agent-workspace-admin", "knowledge-admin", "tooling-admin"]',
        True,
    ),
    "enterprise-admin": (
        "Enterprise administrator",
        '["access-manager", "agent-workspace-manager", "knowledge-manager", "tooling-user"]',
        False,
    ),
    "enduser": (
        "End user",
        '["account-self-service", "agent-workspace-user", "knowledge-search-user", "tooling-user"]',
        False,
    ),
}


def _upsert_role(name: str, description: str, role_ids: str, is_admin: bool) -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO composite_roles
                (name, description, permissions, role_ids, is_builtin, is_admin)
            VALUES
                (:name, :description, '[]'::jsonb, CAST(:role_ids AS jsonb), true, :is_admin)
            ON CONFLICT (name) DO UPDATE
            SET description = EXCLUDED.description,
                permissions = '[]'::jsonb,
                role_ids = EXCLUDED.role_ids,
                is_builtin = true,
                is_admin = EXCLUDED.is_admin
            """
        ).bindparams(name=name, description=description, role_ids=role_ids, is_admin=is_admin)
    )


def upgrade() -> None:
    for name, (description, role_ids, is_admin) in CANONICAL_ROLES.items():
        _upsert_role(name, description, role_ids, is_admin)

    op.execute(
        """
        UPDATE users
        SET role = 'system-admin'
        WHERE role IN ('admin', 'platform-admin')
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'enduser'
        WHERE role NOT IN ('system-admin', 'enterprise-admin', 'enduser')
        """
    )
    op.execute(
        """
        DELETE FROM composite_roles
        WHERE name NOT IN ('system-admin', 'enterprise-admin', 'enduser')
        """
    )


def downgrade() -> None:
    pass
