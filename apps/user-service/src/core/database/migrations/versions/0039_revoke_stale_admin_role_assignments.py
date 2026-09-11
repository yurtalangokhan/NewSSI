"""revoke stale admin role assignments that contradict users.role

`set_user_role` used to APPEND to `user_roles` instead of replacing, so a
user demoted from an admin role kept the old assignment (merely flagged
non-primary). Permission resolution unions across every assigned role, so
those users still resolved to the admin role's permissions - an "enduser"
in the admin Users list who silently retained full admin access.

The code path is fixed (UserRoleRepository.replace_roles), but rows written
before that fix are still in the database. This revokes any admin-tier
assignment held by a user whose authoritative `users.role` is not itself
admin-tier. Non-admin extra assignments are left alone: the multi-role API
(POST /users/{id}/roles + DELETE /users/{id}/roles/{role}) grants those
deliberately.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with src.core.permissions.admin_roles.ADMIN_COMPOSITE_ROLE_NAMES.
# Inlined deliberately: migrations must describe the schema/data as of this
# revision and stay correct even if the application constant changes later.
ADMIN_COMPOSITE_ROLE_NAMES = ("system-admin", "enterprise-admin")


def upgrade() -> None:
    names_sql = ", ".join(f"'{name}'" for name in ADMIN_COMPOSITE_ROLE_NAMES)
    connection = op.get_bind()

    stale = connection.execute(
        sa.text(
            f"""
            SELECT u.email, ur.role_name, u.role AS authoritative_role
            FROM user_roles ur
            JOIN users u ON u.id = ur.user_id
            WHERE ur.role_name IN ({names_sql})
              AND u.role NOT IN ({names_sql})
            """
        )
    ).fetchall()

    for email, role_name, authoritative_role in stale:
        print(
            f"Migration 0039: revoking stale '{role_name}' assignment from "
            f"{email} (authoritative role: '{authoritative_role}')"
        )

    result = connection.execute(
        sa.text(
            f"""
            DELETE FROM user_roles ur
            USING users u
            WHERE u.id = ur.user_id
              AND ur.role_name IN ({names_sql})
              AND u.role NOT IN ({names_sql})
            """
        )
    )

    print(f"Migration 0039: revoked {result.rowcount or 0} stale admin role assignment(s)")


def downgrade() -> None:
    # Intentionally not reversible: restoring revoked admin assignments would
    # re-grant privileges that were never meant to be held.
    pass
