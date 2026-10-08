"""Let the database guarantee one live sync job per datasource.

The sync runner checks for a running job and then creates its own. Two replicas
handling a trigger for the same datasource at the same moment could both pass
that check. A partial unique index over the non-terminal jobs makes the second
insert lose (``ConnectorSyncJobRepository.create_exclusive``).

Should older rows already break the rule, all but the newest live job of a
datasource are closed first so the index can be built.

Revision ID: 0052
Revises: 0051
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE connector_sync_jobs
        SET status = 'failed',
            error = 'superseded by a newer sync job',
            finished_at = now()
        WHERE status IN ('pending', 'running')
          AND id NOT IN (
              SELECT DISTINCT ON (datasource_id) id
              FROM connector_sync_jobs
              WHERE status IN ('pending', 'running')
              ORDER BY datasource_id, created_at DESC
          )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_connector_sync_jobs_active
        ON connector_sync_jobs (datasource_id)
        WHERE status IN ('pending', 'running')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_connector_sync_jobs_active")
