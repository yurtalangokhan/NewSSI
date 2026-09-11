"""drop legacy composite_roles.is_admin column

`is_admin` was a per-row flag that had to be kept in sync by hand every
time the canonical admin roles were reconciled (see migrations 0028/0029).
Admin-tier membership is now determined by checking a composite role's
`name` against the canonical set in `src.core.permissions.admin_roles`
(currently "system-admin" and "enterprise-admin"), so the column is no
longer read anywhere and is dropped here.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADMIN_COMPOSITE_ROLE_NAMES = ("system-admin", "enterprise-admin")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("composite_roles", "is_admin"):
        op.drop_column("composite_roles", "is_admin")


def downgrade() -> None:
    op.add_column(
        "composite_roles",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )
    names_sql = ", ".join(f"'{name}'" for name in ADMIN_COMPOSITE_ROLE_NAMES)
    op.execute(f"UPDATE composite_roles SET is_admin = true WHERE name IN ({names_sql})")
