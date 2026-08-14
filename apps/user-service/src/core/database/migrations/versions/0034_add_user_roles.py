"""add user role assignment table

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-14 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_name", sa.String(length=50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_name"], ["composite_roles.name"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_name"),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_name", "user_roles", ["role_name"])
    op.create_index("ix_user_roles_primary", "user_roles", ["user_id", "is_primary"])
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_name, is_primary, created_at)
        SELECT users.id, users.role, true, now()
        FROM users
        JOIN composite_roles ON composite_roles.name = users.role
        ON CONFLICT (user_id, role_name) DO UPDATE SET is_primary = true
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_roles_primary", table_name="user_roles")
    op.drop_index("ix_user_roles_role_name", table_name="user_roles")
    op.drop_index("ix_user_roles_user_id", table_name="user_roles")
    op.drop_table("user_roles")
