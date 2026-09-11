"""Create unified agents table and migrate existing agent records.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            legacy_persona_id INTEGER UNIQUE,
            legacy_assistant_id UUID,
            legacy_definition_id UUID,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            agent_type VARCHAR(50) NOT NULL DEFAULT 'dynamic',
            graph_schema VARCHAR(50) NOT NULL DEFAULT 'zero_shot',
            brain_type VARCHAR(50) NOT NULL DEFAULT 'llm',
            memory_type VARCHAR(50) NOT NULL DEFAULT 'none',
            system_prompt TEXT,
            task_prompt TEXT,
            model VARCHAR(100),
            datetime_aware BOOLEAN NOT NULL DEFAULT TRUE,
            is_public BOOLEAN NOT NULL DEFAULT TRUE,
            llm_model_provider_override TEXT,
            llm_model_version_override TEXT,
            starter_messages JSONB,
            labels JSONB,
            rag_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            mcp_tools JSONB NOT NULL DEFAULT '[]'::jsonb,
            mcp_tool_configs JSONB NOT NULL DEFAULT '{}'::jsonb,
            sub_agents JSONB NOT NULL DEFAULT '[]'::jsonb,
            sub_agent_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            sub_agent_config_version INTEGER NOT NULL DEFAULT 0,
            supervisor_prompt TEXT,
            stages JSONB NOT NULL DEFAULT '[]'::jsonb,
            pipeline_prompt TEXT,
            reflection_prompt TEXT,
            max_iterations INTEGER NOT NULL DEFAULT 3,
            version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            user_id TEXT NOT NULL DEFAULT 'dev-user',
            is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
            builtin_key TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agents_type ON agents (agent_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agents_user_id ON agents (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agents_active ON agents (is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agents_name ON agents (name)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agents_legacy_persona_id ON agents (legacy_persona_id)"
    )

    op.execute(
        """
        INSERT INTO agents (
            legacy_persona_id, name, description, agent_type, graph_schema,
            system_prompt, task_prompt, datetime_aware, is_public,
            llm_model_provider_override, llm_model_version_override, starter_messages,
            labels, rag_config, mcp_tools, mcp_tool_configs, user_id, is_builtin,
            builtin_key, is_active, created_at, updated_at
        )
        SELECT
            id, name, description, 'persona', COALESCE(base_agent, 'zero_shot'),
            system_prompt, task_prompt, datetime_aware, is_public,
            llm_model_provider_override, llm_model_version_override, starter_messages,
            labels, COALESCE(rag_config, '{}'::jsonb), COALESCE(mcp_tools, '[]'::jsonb),
            COALESCE(mcp_tool_configs, '{}'::jsonb), user_id, is_builtin,
            builtin_key, TRUE, time_created, time_updated
        FROM persona
        ON CONFLICT (legacy_persona_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO agents (
            legacy_assistant_id, name, description, agent_type, graph_schema,
            rag_config, user_id, created_at, updated_at
        )
        SELECT
            assistant_id, COALESCE(name, graph_id), NULL, 'assistant', graph_id,
            COALESCE(config, '{}'::jsonb), 'dev-user', created_at, updated_at
        FROM assistant
        WHERE NOT EXISTS (
            SELECT 1 FROM agents WHERE agents.legacy_assistant_id = assistant.assistant_id
        )
        """
    )
    op.execute(
        """
        INSERT INTO agents (
            legacy_definition_id, name, description, agent_type,
            graph_schema, brain_type, memory_type, system_prompt, model,
            rag_config, mcp_tools, mcp_tool_configs, sub_agents, sub_agent_ids,
            sub_agent_config_version, supervisor_prompt, stages, pipeline_prompt,
            reflection_prompt, max_iterations, version, tags, is_active,
            created_at, updated_at
        )
        SELECT
            id, name, description, agent_type, graph_schema,
            brain_type, memory_type, system_prompt, model,
            COALESCE(rag_config::jsonb, '{}'::jsonb), COALESCE(mcp_tools::jsonb, '[]'::jsonb),
            COALESCE(mcp_tool_configs::jsonb, '{}'::jsonb),
            COALESCE(sub_agents::jsonb, '[]'::jsonb),
            COALESCE(sub_agent_ids, '[]'::jsonb), COALESCE(sub_agent_config_version, 0),
            supervisor_prompt, COALESCE(stages::jsonb, '[]'::jsonb), pipeline_prompt,
            reflection_prompt, COALESCE(max_iterations, 3), version,
            COALESCE(tags::jsonb, '[]'::jsonb), is_active, created_at, updated_at
        FROM agent_definitions
        WHERE NOT EXISTS (
            SELECT 1 FROM agents WHERE agents.legacy_definition_id = agent_definitions.id
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agents CASCADE")
