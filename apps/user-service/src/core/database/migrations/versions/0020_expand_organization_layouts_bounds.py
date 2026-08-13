"""Expand organization_layouts position bounds.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-12 00:00:00.000000
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_organization_layouts_position_x_bounds", "organization_layouts", type_="check"
    )
    op.drop_constraint(
        "ck_organization_layouts_position_y_bounds", "organization_layouts", type_="check"
    )
    op.create_check_constraint(
        "ck_organization_layouts_position_x_bounds",
        "organization_layouts",
        "position_x >= -100000000 AND position_x <= 100000000",
    )
    op.create_check_constraint(
        "ck_organization_layouts_position_y_bounds",
        "organization_layouts",
        "position_y >= -100000000 AND position_y <= 100000000",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_organization_layouts_position_x_bounds", "organization_layouts", type_="check"
    )
    op.drop_constraint(
        "ck_organization_layouts_position_y_bounds", "organization_layouts", type_="check"
    )
    op.create_check_constraint(
        "ck_organization_layouts_position_x_bounds",
        "organization_layouts",
        "position_x >= -1000000 AND position_x <= 1000000",
    )
    op.create_check_constraint(
        "ck_organization_layouts_position_y_bounds",
        "organization_layouts",
        "position_y >= -1000000 AND position_y <= 1000000",
    )
