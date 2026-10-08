"""Remove obsolete organization canvas coordinate storage.

Revision ID: 0048
Revises: 0047
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("organization_layouts")


def downgrade() -> None:
    op.create_table(
        "organization_layouts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "position_x >= -100000000 AND position_x <= 100000000",
            name="ck_organization_layouts_position_x_bounds",
        ),
        sa.CheckConstraint(
            "position_y >= -100000000 AND position_y <= 100000000",
            name="ck_organization_layouts_position_y_bounds",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )
