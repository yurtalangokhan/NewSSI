"""Add default_provider_id column to user_settings table.

This allows storing the default provider separately from the default model,
enabling better query performance and data normalization.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-12 10:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add default_provider_id column to user_settings."""
    op.add_column(
        "user_settings",
        sa.Column("default_provider_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Remove default_provider_id column from user_settings."""
    op.drop_column("user_settings", "default_provider_id")
