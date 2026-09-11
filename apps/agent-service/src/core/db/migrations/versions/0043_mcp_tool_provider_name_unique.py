"""Add UNIQUE(provider_id, name) to mcp_tool so tool sync can upsert.

``MCPToolRepository.bulk_upsert`` / ``upsert`` use
``ON CONFLICT (provider_id, name) DO UPDATE`` but no such constraint existed,
so every sync silently wrote zero rows.

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "uq_mcp_tool_provider_name"


def upgrade() -> None:
    # Collapse any pre-existing duplicates, keeping the lowest int_id per pair.
    op.execute(
        """
        DELETE FROM mcp_tool a
        USING mcp_tool b
        WHERE a.provider_id = b.provider_id
          AND a.name = b.name
          AND a.int_id > b.int_id
        """
    )
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_unique_constraints("mcp_tool")}
    if _CONSTRAINT not in existing:
        op.create_unique_constraint(_CONSTRAINT, "mcp_tool", ["provider_id", "name"])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "mcp_tool", type_="unique")
