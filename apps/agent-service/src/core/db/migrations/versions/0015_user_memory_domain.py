"""Alembic migration: introduce the user_memory domain.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-14

Three operations in one migration:
1. Create ``user_memory`` table with a unique index on (user_id, lower(content)).
2. Migrate existing JSONB data from ``user_settings.memories`` into ``user_memory``.
3. Add toggle columns to ``user_settings`` and ``persona``; drop ``memories`` JSONB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create user_memory table
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memory (
            id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     TEXT            NOT NULL,
            content     TEXT            NOT NULL,
            source      VARCHAR(20)     NOT NULL DEFAULT 'manual'
                        CHECK (source IN ('manual', 'auto_extracted', 'imported')),
            time_created TIMESTAMPTZ    NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ    NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_memory_user_id "
        "ON user_memory (user_id, time_created DESC)"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_memory_user_content_lower "
        "ON user_memory (user_id, lower(content))"
    )

    # ------------------------------------------------------------------
    # 2. Migrate JSONB memories → user_memory (best-effort; skips dupes)
    # ------------------------------------------------------------------
    op.execute(
        """
        INSERT INTO user_memory (id, user_id, content, source, time_created, time_updated)
        SELECT
            gen_random_uuid(),
            us.user_id,
            trim((m->>'content')::text),
            'manual',
            us.time_created,
            us.time_created
        FROM user_settings us
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE jsonb_typeof(us.memories)
                WHEN 'array' THEN us.memories
                ELSE '[]'::jsonb
            END
        ) m
        WHERE (m->>'content') IS NOT NULL
          AND length(trim((m->>'content')::text)) > 0
        ON CONFLICT (user_id, lower(content)) DO NOTHING
        """
    )

    # ------------------------------------------------------------------
    # 3a. Add toggle columns to user_settings
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS long_term_memory_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ------------------------------------------------------------------
    # 3b. Add toggle column to persona
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE persona "
        "ADD COLUMN IF NOT EXISTS long_term_memory BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ------------------------------------------------------------------
    # 3c. Drop the old JSONB column from user_settings
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE user_settings DROP COLUMN IF EXISTS memories")


def downgrade() -> None:
    # Re-add memories JSONB column
    op.execute(
        "ALTER TABLE user_settings "
        "ADD COLUMN IF NOT EXISTS memories JSONB NOT NULL DEFAULT '[]'::jsonb"
    )

    # Restore JSONB data from user_memory (manual entries only)
    op.execute(
        """
        UPDATE user_settings us
        SET memories = sub.arr
        FROM (
            SELECT
                user_id,
                jsonb_agg(
                    jsonb_build_object('content', content)
                    ORDER BY time_created ASC
                ) AS arr
            FROM user_memory
            WHERE source = 'manual'
            GROUP BY user_id
        ) sub
        WHERE us.user_id = sub.user_id
        """
    )

    # Drop the new columns
    op.execute(
        "ALTER TABLE user_settings DROP COLUMN IF EXISTS long_term_memory_enabled"
    )
    op.execute("ALTER TABLE persona DROP COLUMN IF EXISTS long_term_memory")

    # Drop the user_memory table
    op.execute("DROP TABLE IF EXISTS user_memory")
