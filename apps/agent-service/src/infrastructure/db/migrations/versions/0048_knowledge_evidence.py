"""Add knowledge_evidence: what each knowledge retrieval call handed the model.

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_evidence (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES thread (thread_id) ON DELETE CASCADE,
            kind VARCHAR(16) NOT NULL,
            tool VARCHAR(64) NOT NULL,
            schema_version SMALLINT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_evidence_thread_id ON knowledge_evidence (thread_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_evidence_thread_id")
    op.execute("DROP TABLE IF EXISTS knowledge_evidence")
