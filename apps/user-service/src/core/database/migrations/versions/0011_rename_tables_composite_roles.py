"""rename roles → composite_roles, coarse_roles → roles

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-26

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Rename column on composite_roles (old roles table)
    # First alter the column type to rename (PostgreSQL ALTER TABLE RENAME COLUMN)
    op.rename_table("roles", "composite_roles")
    op.rename_table("coarse_roles", "roles")
    op.alter_column("composite_roles", "coarse_roles", new_column_name="role_ids")


def downgrade() -> None:
    op.alter_column("composite_roles", "role_ids", new_column_name="coarse_roles")
    op.rename_table("composite_roles", "roles")
    op.rename_table("roles", "coarse_roles")
