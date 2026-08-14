"""Add sub_agent_ids and sub_agent_config_version to agent_definitions.

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-17

This migration adds support for dynamic sub-agent references, enabling agents to
reference other agents by ID instead of inlining their full configurations.

Changes:
- Add sub_agent_ids column (JSONB array of UUIDs) to store references
- Add sub_agent_config_version column (INT) for cache validation
- Create index on sub_agent_ids for fast lookups (GIN for PostgreSQL)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration."""
    # Add sub_agent_ids column (idempotent - skip if exists)
    try:
        op.add_column(
            "agent_definitions",
            sa.Column(
                "sub_agent_ids",
                postgresql.JSONB(),
                nullable=False,
                server_default="[]",
            ),
        )
    except Exception as e:
        # Column might already exist - log and continue
        print(f"sub_agent_ids column creation: {e}")

    # Add sub_agent_config_version column (idempotent - skip if exists)
    try:
        op.add_column(
            "agent_definitions",
            sa.Column(
                "sub_agent_config_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    except Exception as e:
        # Column might already exist - log and continue
        print(f"sub_agent_config_version column creation: {e}")

    # Create index for fast lookups (idempotent - skip if exists)
    try:
        op.create_index(
            "ix_agent_definitions_sub_agent_ids",
            "agent_definitions",
            ["sub_agent_ids"],
            postgresql_using="gin",  # GIN index for JSON arrays
        )
    except Exception as e:
        # Index might already exist - log and continue
        print(f"GIN index creation: {e}")


def downgrade() -> None:
    """Revert the migration."""
    # Drop index (safe - will skip if doesn't exist)
    try:
        op.drop_index(
            "ix_agent_definitions_sub_agent_ids",
            table_name="agent_definitions",
        )
    except Exception as e:
        print(f"Index drop: {e}")

    # Drop columns (safe - will skip if don't exist)
    try:
        op.drop_column("agent_definitions", "sub_agent_ids")
    except Exception as e:
        print(f"sub_agent_ids drop: {e}")

    try:
        op.drop_column("agent_definitions", "sub_agent_config_version")
    except Exception as e:
        print(f"sub_agent_config_version drop: {e}")
