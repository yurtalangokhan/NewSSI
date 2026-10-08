"""Add flow_spec column to agent_definitions for the canvas flow editor.

Additive and nullable — existing rows stay NULL and keep running their
classic graph_schema untouched. In P1 this column IS the flow (no
draft/published distinction yet); P3 re-points it to a denormalized read
cache of the published row in a new agent_flow_versions table, written only
inside the publish transaction. See .tmp/flow-canvas-design.md section 5.1.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_definitions
        ADD COLUMN IF NOT EXISTS flow_spec JSON NULL DEFAULT NULL
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE agent_definitions DROP COLUMN IF EXISTS flow_spec")
