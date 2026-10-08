"""Move datasource syncs from Airbyte to in-process connectors.

Syncs now run inside agent-service through ``packages/connector-py``:

* ``datasource_connections`` replaces ``datasource_airbyte_mapping``. It records
  which connector fills a datasource, the configured stream catalog, and a
  pointer (``config_id``) to the encrypted configuration user-service keeps for
  ``owner_user_id``. No credential is stored in this database.
* ``connector_sync_jobs`` and ``connector_sync_state`` hold what Airbyte's own
  database used to: the job history and the incremental checkpoints.
* ``sync_schedules`` is unchanged; it becomes the scheduler's durable store.

The Airbyte mapping is dropped without a data copy. A mapped datasource pointed
at an Airbyte source whose configuration lived in Airbyte's database in that
connector's own shape, so there is nothing here to convert it from. Existing
collections keep their chunks and need a configuration re-entered before they
sync again.

Saved flows that reference the ``AirbyteDatasource`` component are rewritten to
its new type, ``ConnectorDatasource``.

Revision ID: 0051
Revises: 0050
"""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_OLD_NODE = '"AirbyteDatasource"'
_NEW_NODE = '"ConnectorDatasource"'


def _rename_flow_nodes(old: str, new: str) -> None:
    # Table and node names are the literals in this module, never input.
    for table in ("agent_flow_versions", "agent_definitions"):
        statement = (
            f"UPDATE {table} "
            f"SET flow_spec = replace(flow_spec::text, '{old}', '{new}')::json "
            f"WHERE flow_spec IS NOT NULL AND flow_spec::text LIKE '%{old}%'"
        )
        op.execute(statement)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS datasource_connections (
            datasource_id    UUID PRIMARY KEY
                             REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            connector_name   VARCHAR NOT NULL,
            config_id        UUID NOT NULL,
            owner_user_id    VARCHAR NOT NULL,
            catalog          JSONB NOT NULL DEFAULT '{}'::jsonb,
            update_graph_rag BOOLEAN NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS connector_sync_jobs (
            id            UUID PRIMARY KEY,
            datasource_id UUID NOT NULL
                          REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            status        TEXT NOT NULL,
            trigger       TEXT NOT NULL DEFAULT 'manual',
            stats         JSONB NOT NULL DEFAULT '{}'::jsonb,
            error         TEXT,
            worker_id     TEXT,
            heartbeat_at  TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at    TIMESTAMPTZ,
            finished_at   TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_connector_sync_jobs_datasource_created
        ON connector_sync_jobs (datasource_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_connector_sync_jobs_active
        ON connector_sync_jobs (status) WHERE status IN ('pending', 'running')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS connector_sync_state (
            datasource_id UUID PRIMARY KEY
                          REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            state         JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("DROP TABLE IF EXISTS datasource_airbyte_mapping")
    _rename_flow_nodes(_OLD_NODE, _NEW_NODE)


def downgrade() -> None:
    _rename_flow_nodes(_NEW_NODE, _OLD_NODE)
    op.execute("""
        CREATE TABLE IF NOT EXISTS datasource_airbyte_mapping (
            datasource_id           UUID PRIMARY KEY
                                    REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
            airbyte_source_id       VARCHAR NOT NULL,
            airbyte_connection_id   VARCHAR NOT NULL,
            airbyte_destination_id  VARCHAR NOT NULL,
            update_graph_rag        BOOLEAN NOT NULL DEFAULT FALSE,
            last_processed_job_id   BIGINT NOT NULL DEFAULT 0,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("DROP TABLE IF EXISTS connector_sync_state")
    op.execute("DROP INDEX IF EXISTS idx_connector_sync_jobs_active")
    op.execute("DROP INDEX IF EXISTS idx_connector_sync_jobs_datasource_created")
    op.execute("DROP TABLE IF EXISTS connector_sync_jobs")
    op.execute("DROP TABLE IF EXISTS datasource_connections")
