"""add rag_config column to persona table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17

Stores per-persona RAG configuration:
  {"document_processing": [...uuids], "knowledge_graph": [...uuids]}
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE persona ADD COLUMN IF NOT EXISTS rag_config JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS rag_config")
