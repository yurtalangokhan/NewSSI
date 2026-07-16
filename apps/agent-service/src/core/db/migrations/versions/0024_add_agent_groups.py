"""Add agent access groups.

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_groups (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            user_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            persona_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by VARCHAR(255),
            time_created TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_groups_name ON agent_groups (name)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_groups")
