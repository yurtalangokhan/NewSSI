"""Remove obsolete organization membership role storage."""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_org_role")
    op.execute("DROP INDEX IF EXISTS ix_user_organizations_role_in_org")
    op.drop_column("user_organizations", "role_in_org")


def downgrade() -> None:
    # Old membership role values cannot be reconstructed from global role assignments.
    op.add_column(
        "user_organizations",
        sa.Column("role_in_org", sa.String(100), nullable=False, server_default="member"),
    )
    op.create_index("ix_user_organizations_role_in_org", "user_organizations", ["role_in_org"])
    op.create_index("idx_user_org_role", "user_organizations", ["user_id", "organization_id", "role_in_org"])
