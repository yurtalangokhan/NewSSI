"""Add agent_flow_versions table + agent_definitions.published_flow_version_id.

Pure schema, additive, no behavior change (P3 Task 14). Nothing reads or
writes this table yet — existing flow-backed agents keep running exactly as
they do today, from agent_definitions.flow_spec directly. Backfilling
existing flows into version 1 rows is Task 16's migration (0033), which also
re-points flow_spec to mean "published cache". See
.tmp/flow-canvas-design.md section 5.1.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_flow_versions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            definition_id UUID NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            flow_spec JSON NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            created_by VARCHAR(255),
            published_by VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            published_at TIMESTAMP,
            notes TEXT,
            CONSTRAINT uq_agent_flow_versions_def_version UNIQUE (definition_id, version_no)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_agent_flow_versions_definition_id
        ON agent_flow_versions (definition_id)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_flow_versions_one_draft_per_definition
        ON agent_flow_versions (definition_id) WHERE status = 'draft'
    """)
    op.execute("""
        ALTER TABLE agent_definitions
        ADD COLUMN IF NOT EXISTS published_flow_version_id UUID
        REFERENCES agent_flow_versions(id) ON DELETE SET NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE agent_definitions DROP COLUMN IF EXISTS published_flow_version_id")
    op.execute("DROP TABLE IF EXISTS agent_flow_versions")
