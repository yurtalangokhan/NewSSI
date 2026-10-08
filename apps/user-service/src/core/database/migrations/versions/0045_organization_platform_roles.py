"""Backfill missing platform assignments before organization role reads switch sources."""

from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        INSERT INTO user_roles (user_id, role_name, is_primary, created_at)
        SELECT users.id, users.role, true, CURRENT_TIMESTAMP
        FROM users
        JOIN composite_roles ON composite_roles.name = users.role
        WHERE NOT EXISTS (SELECT 1 FROM user_roles WHERE user_roles.user_id = users.id)
        ON CONFLICT (user_id, role_name) DO NOTHING
    """)
    )


def downgrade() -> None:
    # Assignment provenance is not stored; deleting rows could revoke later grants.
    pass
