"""Add dynamic agent tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-22

Adds:
  - agent_definitions  (new schema: graph_schema, brain_type, memory_type, system_prompt,
                        model, mcp_tools, sub_agents, supervisor_prompt, stages,
                        pipeline_prompt, reflection_prompt, max_iterations)
  - agent_instances    (unchanged structure, created IF NOT EXISTS)
  - agent_sub_agents   (unchanged structure, created IF NOT EXISTS)
  - agent_pipeline_stages (unchanged structure, created IF NOT EXISTS)

Backward-compatible strategy
------------------------------
* agent_definitions may already exist with the OLD schema (class_path, config_schema,
  default_config columns and no graph_schema/brain_type/etc.).
* We use CREATE TABLE IF NOT EXISTS so the table is created fresh if missing,
  then ADD COLUMN IF NOT EXISTS for every new column so an existing old-schema
  table is safely migrated.
* Old columns (class_path, config_schema, default_config) are NOT dropped so any
  existing rows remain readable.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # agent_definitions
    # -------------------------------------------------------------------------
    # Create with full new schema if the table does not exist yet.
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_definitions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        VARCHAR(100) UNIQUE NOT NULL,
            agent_type  VARCHAR(50)  NOT NULL DEFAULT 'dynamic',
            description TEXT,
            graph_schema   VARCHAR(50) NOT NULL DEFAULT 'zero_shot',
            brain_type     VARCHAR(50) NOT NULL DEFAULT 'llm',
            memory_type    VARCHAR(50) NOT NULL DEFAULT 'none',
            system_prompt  TEXT,
            model          VARCHAR(100),
            mcp_tools      JSONB       NOT NULL DEFAULT '[]',
            sub_agents     JSONB       NOT NULL DEFAULT '[]',
            supervisor_prompt TEXT,
            stages         JSONB       NOT NULL DEFAULT '[]',
            pipeline_prompt   TEXT,
            reflection_prompt TEXT,
            max_iterations    INTEGER NOT NULL DEFAULT 3,
            version        VARCHAR(20) NOT NULL DEFAULT '1.0.0',
            tags           JSONB       NOT NULL DEFAULT '[]',
            is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMP   NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMP   NOT NULL DEFAULT NOW()
        )
    """)

    # Add new columns in case the table existed with the OLD schema.
    # ADD COLUMN IF NOT EXISTS is idempotent.
    new_columns = [
        ("graph_schema",       "VARCHAR(50) NOT NULL DEFAULT 'zero_shot'"),
        ("brain_type",         "VARCHAR(50) NOT NULL DEFAULT 'llm'"),
        ("memory_type",        "VARCHAR(50) NOT NULL DEFAULT 'none'"),
        ("system_prompt",      "TEXT"),
        ("model",              "VARCHAR(100)"),
        ("mcp_tools",          "JSONB NOT NULL DEFAULT '[]'"),
        ("sub_agents",         "JSONB NOT NULL DEFAULT '[]'"),
        ("supervisor_prompt",  "TEXT"),
        ("stages",             "JSONB NOT NULL DEFAULT '[]'"),
        ("pipeline_prompt",    "TEXT"),
        ("reflection_prompt",  "TEXT"),
        ("max_iterations",     "INTEGER NOT NULL DEFAULT 3"),
        ("tags",               "JSONB NOT NULL DEFAULT '[]'"),
    ]
    for col_name, col_def in new_columns:
        op.execute(
            f"ALTER TABLE agent_definitions ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
        )

    # Indexes (use CREATE INDEX IF NOT EXISTS - safe to re-run)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_definitions_type "
        "ON agent_definitions (agent_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_definitions_graph_schema "
        "ON agent_definitions (graph_schema)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_definitions_active "
        "ON agent_definitions (is_active)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_definitions_name "
        "ON agent_definitions (name)"
    )

    # -------------------------------------------------------------------------
    # agent_instances
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_instances (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            definition_id   UUID NOT NULL,
            user_id         VARCHAR(100),
            runtime_config  JSONB NOT NULL DEFAULT '{}',
            state           JSONB NOT NULL DEFAULT '{}',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            last_used_at    TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_instances_definition "
        "ON agent_instances (definition_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_instances_user "
        "ON agent_instances (user_id)"
    )

    # -------------------------------------------------------------------------
    # agent_sub_agents
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_sub_agents (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manager_id  UUID NOT NULL,
            name        VARCHAR(100) NOT NULL,
            system_prompt TEXT,
            mcp_tools   JSONB NOT NULL DEFAULT '[]',
            model       VARCHAR(50),
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sub_agents_manager "
        "ON agent_sub_agents (manager_id)"
    )

    # -------------------------------------------------------------------------
    # agent_pipeline_stages
    # -------------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_pipeline_stages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pipeline_id UUID NOT NULL,
            name        VARCHAR(100) NOT NULL,
            system_prompt TEXT,
            mcp_tools   JSONB NOT NULL DEFAULT '[]',
            model       VARCHAR(50),
            stage_order INTEGER NOT NULL DEFAULT 0,
            on_error    VARCHAR(20) NOT NULL DEFAULT 'abort',
            retry_count INTEGER NOT NULL DEFAULT 2,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline "
        "ON agent_pipeline_stages (pipeline_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_pipeline_stages")
    op.execute("DROP TABLE IF EXISTS agent_sub_agents")
    op.execute("DROP TABLE IF EXISTS agent_instances")
    # NOTE: We do NOT drop agent_definitions on downgrade to preserve any existing data.
    # To fully revert, run: DROP TABLE agent_definitions;
