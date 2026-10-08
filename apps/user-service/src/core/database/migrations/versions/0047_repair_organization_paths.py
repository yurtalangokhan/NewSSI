"""Rebuild organization paths and levels from authoritative parent links."""

from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
        WITH RECURSIVE hierarchy AS (
            SELECT id, CAST('/' AS VARCHAR(1000)) AS path, 0 AS level
            FROM organizations WHERE parent_id IS NULL
            UNION ALL
            SELECT child.id,
                   CAST(parent.path || CAST(parent.id AS TEXT) || '/' AS VARCHAR(1000)),
                   parent.level + 1
            FROM organizations child JOIN hierarchy parent ON child.parent_id = parent.id
        )
        UPDATE organizations SET path = hierarchy.path, level = hierarchy.level
        FROM hierarchy WHERE organizations.id = hierarchy.id
    """)
    )


def downgrade() -> None:
    # Prior corrupt paths cannot be reconstructed and must not be restored.
    pass
