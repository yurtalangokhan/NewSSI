"""Drop unused agent tables — data is stored as JSONB on agent_definitions.

The agent_instances, agent_sub_agents, and agent_pipeline_stages tables
were created in migration 0005 but never used at runtime:
- Sub-agents and pipeline stages are stored as JSONB columns on agent_definitions
- Agent instances are managed in-memory by AgentInstanceManager and LangGraph checkpoints
- No route, controller, or service references any of these tables

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_pipeline_stages CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_sub_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_instances CASCADE")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_instances (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            definition_id      UUID NOT NULL,
            user_id            VARCHAR(100),
            runtime_config     JSONB DEFAULT '{}'::jsonb,
            state              JSONB DEFAULT '{}'::jsonb,
            is_active          BOOLEAN DEFAULT TRUE,
            created_at         TIMESTAMP DEFAULT now(),
            updated_at         TIMESTAMP DEFAULT now(),
            last_used_at       TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_instances_definition ON agent_instances (definition_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_instances_user ON agent_instances (user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sub_agents (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manager_id         UUID NOT NULL,
            name               VARCHAR(100) NOT NULL,
            system_prompt      TEXT,
            mcp_tools          JSONB DEFAULT '[]'::jsonb,
            model              VARCHAR(50),
            order_index        INTEGER DEFAULT 0,
            created_at         TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sub_agents_manager ON agent_sub_agents (manager_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_pipeline_stages (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pipeline_id        UUID NOT NULL,
            name               VARCHAR(100) NOT NULL,
            system_prompt      TEXT,
            mcp_tools          JSONB DEFAULT '[]'::jsonb,
            model              VARCHAR(50),
            stage_order        INTEGER DEFAULT 0,
            on_error           VARCHAR(20) DEFAULT 'abort',
            retry_count        INTEGER DEFAULT 2,
            created_at         TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline ON agent_pipeline_stages (pipeline_id)")
