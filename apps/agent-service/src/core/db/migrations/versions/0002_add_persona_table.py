"""add persona table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS persona (
            id                          SERIAL PRIMARY KEY,
            name                        TEXT NOT NULL,
            description                 TEXT NOT NULL DEFAULT '',
            system_prompt               TEXT NOT NULL DEFAULT '',
            task_prompt                 TEXT NOT NULL DEFAULT '',
            datetime_aware              BOOLEAN NOT NULL DEFAULT TRUE,
            is_public                   BOOLEAN NOT NULL DEFAULT TRUE,
            llm_model_provider_override TEXT,
            llm_model_version_override  TEXT,
            starter_messages            JSONB,
            labels                      JSONB,
            user_id                     TEXT NOT NULL DEFAULT 'dev-user',
            is_builtin                  BOOLEAN NOT NULL DEFAULT FALSE,
            builtin_key                 TEXT,
            base_agent                  TEXT,
            mcp_tools                   JSONB,
            time_created                TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated                TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_persona_user_id ON persona (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_persona_builtin ON persona (is_builtin)
        WHERE is_builtin = TRUE
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS persona CASCADE")
