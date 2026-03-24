"""baseline – create all application tables

Revision ID: 0001
Revises: None
Create Date: 2026-03-12

Creates:
- assistant
- thread
- langchain_pg_collection
- langchain_pg_embedding
- sync_schedules
- datasource_airbyte_mapping

All statements use ``IF NOT EXISTS`` so the migration is safe to run
against a database that already has some or all of these tables
(e.g. tables previously created by raw ``CREATE TABLE IF NOT EXISTS``
SQL at application startup).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # assistant
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS assistant (
            assistant_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            graph_id        VARCHAR NOT NULL,
            name            VARCHAR,
            config          JSONB DEFAULT '{}'::jsonb,
            metadata        JSONB DEFAULT '{}'::jsonb,
            version         INTEGER NOT NULL DEFAULT 1,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # ------------------------------------------------------------------
    # thread
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS thread (
            thread_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            metadata    JSONB DEFAULT '{}'::jsonb,
            status      VARCHAR NOT NULL DEFAULT 'idle',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_thread_metadata_gin
            ON thread USING gin (metadata)
    """)

    # ------------------------------------------------------------------
    # langchain_pg_collection
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS langchain_pg_collection (
            uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR NOT NULL UNIQUE,
            cmetadata   JSON
        )
    """)

    # ------------------------------------------------------------------
    # langchain_pg_embedding
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
            id              VARCHAR PRIMARY KEY,
            collection_id   UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            embedding       TEXT,
            document        VARCHAR,
            cmetadata       JSONB
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cmetadata_gin
            ON langchain_pg_embedding USING gin (cmetadata)
    """)

    # ------------------------------------------------------------------
    # sync_schedules
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_schedules (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            datasource_id   UUID NOT NULL,
            cron_expression TEXT NOT NULL,
            preset          TEXT NOT NULL DEFAULT 'custom',
            enabled         BOOLEAN NOT NULL DEFAULT TRUE,
            update_graph_rag BOOLEAN NOT NULL DEFAULT FALSE,
            timezone        TEXT NOT NULL DEFAULT 'UTC',
            next_run_at     TIMESTAMPTZ,
            last_run_at     TIMESTAMPTZ,
            last_run_status TEXT,
            last_run_error  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_datasource
                FOREIGN KEY (datasource_id)
                REFERENCES langchain_pg_collection(uuid)
                ON DELETE CASCADE,
            CONSTRAINT uq_datasource_schedule
                UNIQUE (datasource_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_schedules_enabled
            ON sync_schedules (enabled) WHERE enabled = TRUE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sync_schedules_next_run
            ON sync_schedules (next_run_at) WHERE enabled = TRUE
    """)

    # ------------------------------------------------------------------
    # datasource_airbyte_mapping
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS datasource_airbyte_mapping (
            datasource_id           UUID PRIMARY KEY,
            airbyte_source_id       VARCHAR NOT NULL,
            airbyte_connection_id   VARCHAR NOT NULL,
            airbyte_destination_id  VARCHAR NOT NULL,
            update_graph_rag        BOOLEAN NOT NULL DEFAULT FALSE,
            last_processed_job_id   BIGINT NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_datasource_mapping
                FOREIGN KEY (datasource_id)
                REFERENCES langchain_pg_collection(uuid)
                ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS datasource_airbyte_mapping CASCADE")
    op.execute("DROP TABLE IF EXISTS sync_schedules CASCADE")
    op.execute("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE")
    op.execute("DROP TABLE IF EXISTS langchain_pg_collection CASCADE")
    op.execute("DROP TABLE IF EXISTS thread CASCADE")
    op.execute("DROP TABLE IF EXISTS assistant CASCADE")
