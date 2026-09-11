"""Drop unused langchain_pg_embedding table from agent-service.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
            id VARCHAR PRIMARY KEY,
            collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            embedding TEXT,
            document VARCHAR,
            cmetadata JSONB
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cmetadata_gin "
        "ON langchain_pg_embedding USING gin (cmetadata)"
    )
