"""Rename created_at/updated_at to time_created/time_updated in MCP tables.

The mcp_provider, mcp_tool, and agent_tools tables were originally created
by migration 0006 with created_at/updated_at column names, but the ORM models
use time_created/time_updated.  This migration renames the columns in-place.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    return column in cols


def upgrade() -> None:
    bind = op.get_bind()

    # ── mcp_provider ──────────────────────────────────────────────
    if _has_column(bind, "mcp_provider", "created_at"):
        op.alter_column("mcp_provider", "created_at", new_column_name="time_created")
    if _has_column(bind, "mcp_provider", "updated_at"):
        op.alter_column("mcp_provider", "updated_at", new_column_name="time_updated")

    # ── mcp_tool ──────────────────────────────────────────────────
    if _has_column(bind, "mcp_tool", "created_at"):
        op.alter_column("mcp_tool", "created_at", new_column_name="time_created")

    # ── agent_tools ───────────────────────────────────────────────
    if _has_column(bind, "agent_tools", "created_at"):
        op.alter_column("agent_tools", "created_at", new_column_name="time_created")


def downgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, "mcp_provider", "time_created"):
        op.alter_column("mcp_provider", "time_created", new_column_name="created_at")
    if _has_column(bind, "mcp_provider", "time_updated"):
        op.alter_column("mcp_provider", "time_updated", new_column_name="updated_at")

    if _has_column(bind, "mcp_tool", "time_created"):
        op.alter_column("mcp_tool", "time_created", new_column_name="created_at")

    if _has_column(bind, "agent_tools", "time_created"):
        op.alter_column("agent_tools", "time_created", new_column_name="created_at")
