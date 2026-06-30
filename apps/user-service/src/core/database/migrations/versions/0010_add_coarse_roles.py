"""add coarse_roles table and column on roles

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-26

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Coarse role seed data — maps each coarse role to its permissions.
# These are service-client roles like tool-admin, user-manager, etc.
# ---------------------------------------------------------------------------

COARSE_ROLES_SEED = [
    # ── user-service ──────────────────────────────────────────────
    {
        "name": "user-admin",
        "description": "Full user management — create, read, update, delete users, roles, permissions, audit logs, groups, API keys",
        "service_client": "user-service",
        "permissions": [
            "api_key:create",
            "api_key:delete",
            "api_key:read",
            "api_key:update",
            "audit_log:export",
            "audit_log:list",
            "audit_log:manage",
            "audit_log:read",
            "group:create",
            "group:delete",
            "group:list",
            "group:manage",
            "group:read",
            "group:update",
            "permission:list",
            "permission:read",
            "role:list",
            "role:read",
            "role:manage",
            "user:create",
            "user:delete",
            "user:list",
            "user:read",
            "user:update",
            "system.settings:read",
            "system.settings:update",
        ],
    },
    {
        "name": "user-manager",
        "description": "Operational user management — read, list, update users; read roles, permissions, audit logs, groups",
        "service_client": "user-service",
        "permissions": [
            "audit_log:export",
            "audit_log:list",
            "audit_log:read",
            "group:list",
            "group:read",
            "permission:list",
            "permission:read",
            "role:list",
            "role:read",
            "user:list",
            "user:read",
            "user:update",
        ],
    },
    {
        "name": "enduser",
        "description": "Basic user-service permissions for end users",
        "service_client": "user-service",
        "permissions": [
            "api_key:create",
            "api_key:delete",
            "api_key:read",
            "api_key:update",
            "user:read",
        ],
    },
    # ── agent-service ─────────────────────────────────────────────
    {
        "name": "agent-admin",
        "description": "Full agent management — create, read, update, delete agents, assistants, conversations, analytics, threads, runs, personas, projects, memories, schedules, agent definitions",
        "service_client": "agent-service",
        "permissions": [
            "agent:assign",
            "agent:create",
            "agent:delete",
            "agent:invoke",
            "agent:list",
            "agent:read",
            "agent:share",
            "agent:stream",
            "agent:update",
            "agent_definition:create",
            "agent_definition:delete",
            "agent_definition:read",
            "agent_definition:update",
            "analytics:export",
            "analytics:read",
            "assistant:create",
            "assistant:delete",
            "assistant:read",
            "assistant:search",
            "assistant:update",
            "conversation:delete",
            "conversation:export",
            "conversation:read",
            "memory:create",
            "memory:delete",
            "memory:read",
            "memory:update",
            "persona:create",
            "persona:delete",
            "persona:read",
            "persona:update",
            "project:create",
            "project:delete",
            "project:read",
            "project:update",
            "run:cancel",
            "run:create",
            "run:read",
            "schedule:create",
            "schedule:delete",
            "schedule:read",
            "schedule:update",
            "thread:create",
            "thread:delete",
            "thread:read",
            "thread:search",
            "thread:update",
            "chat:delete",
            "chat:read",
            "chat:send",
        ],
    },
    {
        "name": "agent-manager",
        "description": "Operational agent management — list, read, create, update agents, assistants, threads, runs, personas, projects",
        "service_client": "agent-service",
        "permissions": [
            "agent:create",
            "agent:invoke",
            "agent:list",
            "agent:read",
            "agent:stream",
            "agent:update",
            "analytics:read",
            "assistant:create",
            "assistant:read",
            "assistant:search",
            "assistant:update",
            "conversation:export",
            "conversation:read",
            "persona:read",
            "project:create",
            "project:delete",
            "project:read",
            "project:update",
            "run:cancel",
            "run:create",
            "run:read",
            "thread:create",
            "thread:delete",
            "thread:read",
            "thread:search",
            "thread:update",
            "chat:delete",
            "chat:read",
            "chat:send",
        ],
    },
    {
        "name": "agent-enduser",
        "description": "End-user agent permissions — invoke agents, read assistants, manage own threads and runs",
        "service_client": "agent-service",
        "permissions": [
            "agent:invoke",
            "agent:list",
            "agent:read",
            "agent:stream",
            "assistant:read",
            "assistant:search",
            "chat:delete",
            "chat:read",
            "chat:send",
            "conversation:export",
            "memory:create",
            "memory:delete",
            "memory:read",
            "memory:update",
            "persona:read",
            "project:create",
            "project:delete",
            "project:read",
            "project:update",
            "run:cancel",
            "run:create",
            "run:read",
            "thread:create",
            "thread:delete",
            "thread:read",
            "thread:search",
            "thread:update",
        ],
    },
    # ── rag-service ───────────────────────────────────────────────
    {
        "name": "rag-admin",
        "description": "Full RAG management — collections, documents, datasources, chunks, embeddings, graphs, web search",
        "service_client": "rag-service",
        "permissions": [
            "chunk:read",
            "chunk:search",
            "collection:create",
            "collection:delete",
            "collection:list",
            "collection:read",
            "collection:update",
            "datasource:create",
            "datasource:delete",
            "datasource:read",
            "datasource:sync",
            "datasource:update",
            "document:create",
            "document:delete",
            "document:read",
            "document:search",
            "document:update",
            "embedding:read",
            "graph:build",
            "graph:delete",
            "graph:read",
            "graph:search",
            "web_search:manage",
            "web_search:test",
        ],
    },
    {
        "name": "rag-manager",
        "description": "Operational RAG management — read, search, create documents and collections, sync datasources",
        "service_client": "rag-service",
        "permissions": [
            "chunk:read",
            "chunk:search",
            "collection:create",
            "collection:list",
            "collection:read",
            "collection:update",
            "datasource:read",
            "datasource:sync",
            "document:create",
            "document:read",
            "document:search",
            "document:update",
            "embedding:read",
            "graph:read",
            "graph:search",
            "web_search:manage",
            "web_search:test",
        ],
    },
    {
        "name": "rag-enduser",
        "description": "End-user RAG permissions — search documents and chunks, read collections, search graph",
        "service_client": "rag-service",
        "permissions": [
            "chunk:read",
            "chunk:search",
            "collection:list",
            "collection:read",
            "datasource:read",
            "document:read",
            "document:search",
            "graph:read",
            "graph:search",
        ],
    },
    # ── tools-service ─────────────────────────────────────────────
    {
        "name": "tool-admin",
        "description": "Full tools management — execute tools, manage MCP tools, providers and all tool configurations",
        "service_client": "tools-service",
        "permissions": [
            "mcp_provider:create",
            "mcp_provider:delete",
            "mcp_provider:read",
            "mcp_provider:sync",
            "mcp_provider:update",
            "mcp_tool:read",
            "mcp_tool:sync",
            "tool:execute",
            "tool:read",
        ],
    },
    {
        "name": "tool-user",
        "description": "Basic tool user — execute tools and read tool/MCP catalog",
        "service_client": "tools-service",
        "permissions": [
            "mcp_provider:read",
            "mcp_tool:read",
            "tool:execute",
            "tool:read",
        ],
    },
]

# ---------------------------------------------------------------------------
# Maps built-in realm roles → list of coarse role names to assign.
# This mirrors what COARSE_SERVICE_ROLES does in role_service.py but is
# stored in DB so it can be managed via the UI.
# ---------------------------------------------------------------------------

REALM_ROLE_COARSE_MAP: dict[str, list[str]] = {
    "system-admin": [
        "user-admin",
        "agent-admin",
        "rag-admin",
        "tool-admin",
    ],
    "enterprise-admin": [
        "user-manager",
        "agent-manager",
        "rag-manager",
        "tool-user",
    ],
    "enduser": [
        "enduser",
        "agent-enduser",
        "rag-enduser",
        "tool-user",
    ],
}


def upgrade() -> None:
    # 1. Create coarse_roles table
    op.create_table(
        "coarse_roles",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("service_client", sa.String(50), nullable=False),
        sa.Column("permissions", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 2. Seed coarse roles
    for cr in COARSE_ROLES_SEED:
        perms_json = json.dumps(sorted(cr["permissions"]))
        op.execute(
            f"""INSERT INTO coarse_roles (name, description, service_client, permissions)
                VALUES ('{cr["name"]}', '{cr["description"]}', '{cr["service_client"]}', '{perms_json}'::jsonb)"""
        )

    print(f"Migration 0010: seeded {len(COARSE_ROLES_SEED)} coarse roles")

    # 3. Add coarse_roles JSONB column to roles table (nullable, defaults to [])
    op.add_column(
        "roles",
        sa.Column("coarse_roles", JSONB, nullable=True, server_default="[]"),
    )

    # 4. Populate coarse_roles on built-in roles
    for role_name, coarse_names in REALM_ROLE_COARSE_MAP.items():
        cr_json = json.dumps(coarse_names)
        op.execute(f"UPDATE roles SET coarse_roles = '{cr_json}'::jsonb WHERE name = '{role_name}'")

    print(f"Migration 0010: updated coarse_roles on {len(REALM_ROLE_COARSE_MAP)} built-in roles")


def downgrade() -> None:
    # Remove coarse_roles column from roles
    op.drop_column("roles", "coarse_roles")

    # Drop coarse_roles table
    op.drop_table("coarse_roles")

    # Clean up built-in role coarse_roles (already dropped by column drop)
    print("Migration 0010: reverted")
