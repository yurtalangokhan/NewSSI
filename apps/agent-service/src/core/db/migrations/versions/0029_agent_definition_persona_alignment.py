"""Align agent definition persona and provider config schema.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_definitions ADD COLUMN IF NOT EXISTS persona_id INTEGER")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'agent_definitions_persona_id_key'
            ) THEN
                ALTER TABLE agent_definitions
                ADD CONSTRAINT agent_definitions_persona_id_key UNIQUE (persona_id);
            END IF;
        END $$;
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_definitions_persona_id "
        "ON agent_definitions (persona_id)"
    )
    op.execute("""
        ALTER TABLE user_provider_configs
        ALTER COLUMN api_key_fingerprint
        TYPE VARCHAR(16)
        USING api_key_fingerprint::varchar(16)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE user_provider_configs
        ALTER COLUMN api_key_fingerprint
        TYPE TEXT
    """)
    op.execute("DROP INDEX IF EXISTS ix_agent_definitions_persona_id")
    op.execute(
        "ALTER TABLE agent_definitions "
        "DROP CONSTRAINT IF EXISTS agent_definitions_persona_id_key"
    )
    op.execute("ALTER TABLE agent_definitions DROP COLUMN IF EXISTS persona_id")
