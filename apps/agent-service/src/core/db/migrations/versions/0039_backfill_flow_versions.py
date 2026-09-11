"""Backfill pre-P3 flow_spec rows into version 1 published rows.

P1/P2-era flow-backed agents have agent_definitions.flow_spec set and no
version history (agent_flow_versions didn't exist yet). Without this
backfill they would read as "never published" after 0032/Task 16 land,
since published_flow_version_id would be NULL — but they are, in fact,
already running in production exactly as-is. This migration makes their
existing state the version 1 published row, changing no behavior:
flow_spec's value is unchanged, only agent_flow_versions gains a row and
published_flow_version_id gains a pointer to it.

created_by/published_by are NULL for these rows — genuinely unknown for
historical data; not fabricated.

Idempotent: the WHERE clause only matches rows that still have
published_flow_version_id IS NULL, so re-running after a first successful
run inserts nothing further.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_NOTE = "Backfilled from pre-P3 flow_spec"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_definitions
        ADD COLUMN IF NOT EXISTS flow_spec JSON NULL DEFAULT NULL
    """)
    op.execute(f"""
        INSERT INTO agent_flow_versions
            (id, definition_id, version_no, flow_spec, status,
             created_by, published_by, created_at, published_at, notes)
        SELECT
            gen_random_uuid(), id, 1, flow_spec, 'published',
            NULL, NULL, created_at, created_at, '{_BACKFILL_NOTE}'
        FROM agent_definitions
        WHERE flow_spec IS NOT NULL
          AND published_flow_version_id IS NULL
    """)
    op.execute(f"""
        UPDATE agent_definitions AS ad
        SET published_flow_version_id = afv.id
        FROM agent_flow_versions AS afv
        WHERE afv.definition_id = ad.id
          AND afv.version_no = 1
          AND afv.notes = '{_BACKFILL_NOTE}'
          AND ad.published_flow_version_id IS NULL
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE agent_definitions AS ad
        SET published_flow_version_id = NULL
        FROM agent_flow_versions AS afv
        WHERE afv.definition_id = ad.id
          AND ad.published_flow_version_id = afv.id
          AND afv.notes = '{_BACKFILL_NOTE}'
    """)
    op.execute(f"DELETE FROM agent_flow_versions WHERE notes = '{_BACKFILL_NOTE}'")
