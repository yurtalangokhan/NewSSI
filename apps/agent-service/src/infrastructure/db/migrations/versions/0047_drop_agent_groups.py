"""Drop agent_groups table.

The Access Groups feature was removed. Its access-control role was already
superseded by the organization/resource-permission system in user-service;
this table was write-only from the admin UI and never read by any
enforcement path.
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_groups_name")
    op.execute("DROP TABLE IF EXISTS agent_groups")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_groups (
            id SERIAL PRIMARY KEY,
            name VARCHAR(120) UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            user_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            persona_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by VARCHAR(255),
            time_created TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_groups_name ON agent_groups (name)")
