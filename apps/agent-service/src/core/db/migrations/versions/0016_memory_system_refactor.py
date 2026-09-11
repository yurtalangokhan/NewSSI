"""Alembic migration: memory system refactor.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-15

Three operations:
1. Drop unused `use_memories` and `enable_memory_tool` columns
2. Add new `extract_memory` column to enable/disable memory extraction independently
3. Update defaults: all three memory toggles now have clear semantics
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop unused columns
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS use_memories")
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS enable_memory_tool")

    # Add new extract_memory column
    # This controls whether the LLM should extract and save new facts
    # (independent of long_term_memory_enabled, which is the master toggle)
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS extract_memory BOOLEAN NOT NULL DEFAULT TRUE"
    )


def downgrade() -> None:
    # Re-add the old columns
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS use_memories BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS enable_memory_tool BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # Drop the new column
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS extract_memory")
