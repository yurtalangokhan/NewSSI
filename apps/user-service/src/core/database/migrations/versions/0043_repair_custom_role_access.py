"""Backfill normalized access rows for custom composite roles.

Revision ID: 0043
Revises: 0041
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_name, permission_name)
        SELECT composite_roles.name, permission_names.value::text
        FROM composite_roles
        CROSS JOIN LATERAL jsonb_array_elements_text(composite_roles.permissions)
            AS permission_names(value)
        WHERE EXISTS (
            SELECT 1 FROM permissions WHERE permissions.name = permission_names.value::text
        )
        ON CONFLICT DO NOTHING
        """
    )
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
    # The inserted rows cannot be distinguished safely from rows that already
    # existed before this repair, so downgrading intentionally preserves them.
    pass
