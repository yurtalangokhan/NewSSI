"""repair organization code unique index after schema repair

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-14 00:00:00.000000

"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_code_key")
    op.execute("DROP INDEX IF EXISTS ix_organizations_code")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_code ON organizations (code)")


def downgrade() -> None:
    """Repair migrations are intentionally non-destructive."""
