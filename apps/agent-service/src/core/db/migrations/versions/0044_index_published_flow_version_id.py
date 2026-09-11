"""Index agent_definitions.published_flow_version_id.

Migration 0032 added the ``published_flow_version_id`` FK column but no
supporting index, so lookups that join or filter agent definitions by their
published flow version do a sequential scan. Additive and reversible.

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_agent_definitions_published_flow_version_id"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {_INDEX}
        ON agent_definitions (published_flow_version_id)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
