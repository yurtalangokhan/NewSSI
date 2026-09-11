"""Persist configured connector references on chat personas."""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE persona ADD COLUMN IF NOT EXISTS connector_bindings "
        "JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS connector_bindings")
