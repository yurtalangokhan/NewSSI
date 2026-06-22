"""add permission catalog and composite roles

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS_SEED = [
    {"name": "user:create", "label": "Create Users", "entity": "user", "service": "user-service", "action": "create"},
    {"name": "user:read", "label": "Read Users", "entity": "user", "service": "user-service", "action": "read"},
    {"name": "user:update", "label": "Update Users", "entity": "user", "service": "user-service", "action": "update"},
    {"name": "user:delete", "label": "Delete Users", "entity": "user", "service": "user-service", "action": "delete"},
    {"name": "user:list", "label": "List Users", "entity": "user", "service": "user-service", "action": "list"},
    {"name": "user:manage", "label": "Manage Users", "entity": "user", "service": "user-service", "action": "manage"},
    {"name": "role:create", "label": "Create Roles", "entity": "role", "service": "user-service", "action": "create"},
    {"name": "role:read", "label": "Read Roles", "entity": "role", "service": "user-service", "action": "read"},
    {"name": "role:update", "label": "Update Roles", "entity": "role", "service": "user-service", "action": "update"},
    {"name": "role:delete", "label": "Delete Roles", "entity": "role", "service": "user-service", "action": "delete"},
    {"name": "role:list", "label": "List Roles", "entity": "role", "service": "user-service", "action": "list"},
    {"name": "role:manage", "label": "Manage Roles", "entity": "role", "service": "user-service", "action": "manage", "is_system": True},
    {"name": "permission:create", "label": "Create Permissions", "entity": "permission", "service": "user-service", "action": "create", "is_system": True},
    {"name": "permission:read", "label": "Read Permissions", "entity": "permission", "service": "user-service", "action": "read"},
    {"name": "permission:update", "label": "Update Permissions", "entity": "permission", "service": "user-service", "action": "update", "is_system": True},
    {"name": "permission:delete", "label": "Delete Permissions", "entity": "permission", "service": "user-service", "action": "delete", "is_system": True},
    {"name": "permission:list", "label": "List Permissions", "entity": "permission", "service": "user-service", "action": "list"},
    {"name": "permission:manage", "label": "Manage Permissions", "entity": "permission", "service": "user-service", "action": "manage", "is_system": True},
    {"name": "settings:read", "label": "Read Settings", "entity": "settings", "service": "user-service", "action": "read"},
    {"name": "settings:update", "label": "Update Settings", "entity": "settings", "service": "user-service", "action": "update"},
    {"name": "memory:create", "label": "Create Memories", "entity": "memory", "service": "user-service", "action": "create"},
    {"name": "memory:read", "label": "Read Memories", "entity": "memory", "service": "user-service", "action": "read"},
    {"name": "memory:update", "label": "Update Memories", "entity": "memory", "service": "user-service", "action": "update"},
    {"name": "memory:delete", "label": "Delete Memories", "entity": "memory", "service": "user-service", "action": "delete"},
    {"name": "api_key:create", "label": "Create API Keys", "entity": "api_key", "service": "user-service", "action": "create"},
    {"name": "api_key:read", "label": "Read API Keys", "entity": "api_key", "service": "user-service", "action": "read"},
    {"name": "api_key:update", "label": "Update API Keys", "entity": "api_key", "service": "user-service", "action": "update"},
    {"name": "api_key:delete", "label": "Delete API Keys", "entity": "api_key", "service": "user-service", "action": "delete"},
    {"name": "audit_log:read", "label": "Read Audit Logs", "entity": "audit_log", "service": "user-service", "action": "read"},
    {"name": "audit_log:list", "label": "List Audit Logs", "entity": "audit_log", "service": "user-service", "action": "list"},
    {"name": "audit_log:export", "label": "Export Audit Logs", "entity": "audit_log", "service": "user-service", "action": "export"},

    {"name": "agent:create", "label": "Create Agents", "entity": "agent", "service": "agent-service", "action": "create"},
    {"name": "agent:read", "label": "Read Agents", "entity": "agent", "service": "agent-service", "action": "read"},
    {"name": "agent:update", "label": "Update Agents", "entity": "agent", "service": "agent-service", "action": "update"},
    {"name": "agent:delete", "label": "Delete Agents", "entity": "agent", "service": "agent-service", "action": "delete"},
    {"name": "agent:list", "label": "List Agents", "entity": "agent", "service": "agent-service", "action": "list"},
    {"name": "agent:invoke", "label": "Invoke Agents", "entity": "agent", "service": "agent-service", "action": "invoke"},
    {"name": "agent:stream", "label": "Stream Agents", "entity": "agent", "service": "agent-service", "action": "stream"},
    {"name": "agent_definition:create", "label": "Create Agent Definitions", "entity": "agent_definition", "service": "agent-service", "action": "create"},
    {"name": "agent_definition:read", "label": "Read Agent Definitions", "entity": "agent_definition", "service": "agent-service", "action": "read"},
    {"name": "agent_definition:update", "label": "Update Agent Definitions", "entity": "agent_definition", "service": "agent-service", "action": "update"},
    {"name": "agent_definition:delete", "label": "Delete Agent Definitions", "entity": "agent_definition", "service": "agent-service", "action": "delete"},
    {"name": "assistant:create", "label": "Create Assistants", "entity": "assistant", "service": "agent-service", "action": "create"},
    {"name": "assistant:read", "label": "Read Assistants", "entity": "assistant", "service": "agent-service", "action": "read"},
    {"name": "assistant:update", "label": "Update Assistants", "entity": "assistant", "service": "agent-service", "action": "update"},
    {"name": "assistant:delete", "label": "Delete Assistants", "entity": "assistant", "service": "agent-service", "action": "delete"},
    {"name": "assistant:search", "label": "Search Assistants", "entity": "assistant", "service": "agent-service", "action": "search"},
    {"name": "thread:create", "label": "Create Threads", "entity": "thread", "service": "agent-service", "action": "create"},
    {"name": "thread:read", "label": "Read Threads", "entity": "thread", "service": "agent-service", "action": "read"},
    {"name": "thread:update", "label": "Update Threads", "entity": "thread", "service": "agent-service", "action": "update"},
    {"name": "thread:delete", "label": "Delete Threads", "entity": "thread", "service": "agent-service", "action": "delete"},
    {"name": "thread:search", "label": "Search Threads", "entity": "thread", "service": "agent-service", "action": "search"},
    {"name": "run:create", "label": "Create Runs", "entity": "run", "service": "agent-service", "action": "create"},
    {"name": "run:read", "label": "Read Runs", "entity": "run", "service": "agent-service", "action": "read"},
    {"name": "run:cancel", "label": "Cancel Runs", "entity": "run", "service": "agent-service", "action": "cancel"},
    {"name": "chat:send", "label": "Send Chat Messages", "entity": "chat", "service": "agent-service", "action": "send"},
    {"name": "chat:read", "label": "Read Chat Messages", "entity": "chat", "service": "agent-service", "action": "read"},
    {"name": "chat:delete", "label": "Delete Chat Messages", "entity": "chat", "service": "agent-service", "action": "delete"},
    {"name": "persona:create", "label": "Create Personas", "entity": "persona", "service": "agent-service", "action": "create"},
    {"name": "persona:read", "label": "Read Personas", "entity": "persona", "service": "agent-service", "action": "read"},
    {"name": "persona:update", "label": "Update Personas", "entity": "persona", "service": "agent-service", "action": "update"},
    {"name": "persona:delete", "label": "Delete Personas", "entity": "persona", "service": "agent-service", "action": "delete"},
    {"name": "provider:create", "label": "Create LLM Providers", "entity": "provider", "service": "agent-service", "action": "create"},
    {"name": "provider:read", "label": "Read LLM Providers", "entity": "provider", "service": "agent-service", "action": "read"},
    {"name": "provider:update", "label": "Update LLM Providers", "entity": "provider", "service": "agent-service", "action": "update"},
    {"name": "provider:delete", "label": "Delete LLM Providers", "entity": "provider", "service": "agent-service", "action": "delete"},
    {"name": "mcp_provider:create", "label": "Create MCP Providers", "entity": "mcp_provider", "service": "agent-service", "action": "create"},
    {"name": "mcp_provider:read", "label": "Read MCP Providers", "entity": "mcp_provider", "service": "agent-service", "action": "read"},
    {"name": "mcp_provider:update", "label": "Update MCP Providers", "entity": "mcp_provider", "service": "agent-service", "action": "update"},
    {"name": "mcp_provider:delete", "label": "Delete MCP Providers", "entity": "mcp_provider", "service": "agent-service", "action": "delete"},
    {"name": "mcp_provider:sync", "label": "Sync MCP Providers", "entity": "mcp_provider", "service": "agent-service", "action": "sync"},
    {"name": "mcp_tool:read", "label": "Read MCP Tools", "entity": "mcp_tool", "service": "agent-service", "action": "read"},
    {"name": "mcp_tool:sync", "label": "Sync MCP Tools", "entity": "mcp_tool", "service": "agent-service", "action": "sync"},
    {"name": "datasource:create", "label": "Create Datasources", "entity": "datasource", "service": "agent-service", "action": "create"},
    {"name": "datasource:read", "label": "Read Datasources", "entity": "datasource", "service": "agent-service", "action": "read"},
    {"name": "datasource:update", "label": "Update Datasources", "entity": "datasource", "service": "agent-service", "action": "update"},
    {"name": "datasource:delete", "label": "Delete Datasources", "entity": "datasource", "service": "agent-service", "action": "delete"},
    {"name": "datasource:sync", "label": "Sync Datasources", "entity": "datasource", "service": "agent-service", "action": "sync"},
    {"name": "schedule:create", "label": "Create Schedules", "entity": "schedule", "service": "agent-service", "action": "create"},
    {"name": "schedule:read", "label": "Read Schedules", "entity": "schedule", "service": "agent-service", "action": "read"},
    {"name": "schedule:update", "label": "Update Schedules", "entity": "schedule", "service": "agent-service", "action": "update"},
    {"name": "schedule:delete", "label": "Delete Schedules", "entity": "schedule", "service": "agent-service", "action": "delete"},
    {"name": "project:create", "label": "Create Projects", "entity": "project", "service": "agent-service", "action": "create"},
    {"name": "project:read", "label": "Read Projects", "entity": "project", "service": "agent-service", "action": "read"},
    {"name": "project:update", "label": "Update Projects", "entity": "project", "service": "agent-service", "action": "update"},
    {"name": "project:delete", "label": "Delete Projects", "entity": "project", "service": "agent-service", "action": "delete"},
    {"name": "web_search:manage", "label": "Manage Web Search Providers", "entity": "web_search", "service": "agent-service", "action": "manage"},
    {"name": "web_search:test", "label": "Test Web Search", "entity": "web_search", "service": "agent-service", "action": "test"},

    {"name": "collection:create", "label": "Create Collections", "entity": "collection", "service": "rag-service", "action": "create"},
    {"name": "collection:read", "label": "Read Collections", "entity": "collection", "service": "rag-service", "action": "read"},
    {"name": "collection:update", "label": "Update Collections", "entity": "collection", "service": "rag-service", "action": "update"},
    {"name": "collection:delete", "label": "Delete Collections", "entity": "collection", "service": "rag-service", "action": "delete"},
    {"name": "collection:list", "label": "List Collections", "entity": "collection", "service": "rag-service", "action": "list"},
    {"name": "document:create", "label": "Upload Documents", "entity": "document", "service": "rag-service", "action": "create"},
    {"name": "document:read", "label": "Read Documents", "entity": "document", "service": "rag-service", "action": "read"},
    {"name": "document:update", "label": "Update Documents", "entity": "document", "service": "rag-service", "action": "update"},
    {"name": "document:delete", "label": "Delete Documents", "entity": "document", "service": "rag-service", "action": "delete"},
    {"name": "document:search", "label": "Search Documents", "entity": "document", "service": "rag-service", "action": "search"},
    {"name": "graph:build", "label": "Build Knowledge Graphs", "entity": "graph", "service": "rag-service", "action": "build"},
    {"name": "graph:read", "label": "Read Knowledge Graphs", "entity": "graph", "service": "rag-service", "action": "read"},
    {"name": "graph:delete", "label": "Delete Knowledge Graphs", "entity": "graph", "service": "rag-service", "action": "delete"},
    {"name": "graph:search", "label": "Search Knowledge Graphs", "entity": "graph", "service": "rag-service", "action": "search"},

    {"name": "tool:read", "label": "Read Tools", "entity": "tool", "service": "tools-service", "action": "read"},
    {"name": "tool:execute", "label": "Execute Tools", "entity": "tool", "service": "tools-service", "action": "execute"},

    {"name": "system.settings:read", "label": "Read System Settings", "entity": "system", "service": "system", "action": "read", "is_system": True},
    {"name": "system.settings:update", "label": "Update System Settings", "entity": "system", "service": "system", "action": "update", "is_system": True},
]

ENTERPRISE_PERMISSIONS = [
    "user:create", "user:read", "user:update", "user:delete", "user:list",
    "role:read", "role:list",
    "permission:read", "permission:list",
    "settings:read", "settings:update",
    "audit_log:read", "audit_log:list",
    "agent:create", "agent:read", "agent:update", "agent:delete", "agent:list",
    "agent_definition:create", "agent_definition:read", "agent_definition:update", "agent_definition:delete",
    "assistant:create", "assistant:read", "assistant:update", "assistant:delete", "assistant:search",
    "thread:create", "thread:read", "thread:update", "thread:delete", "thread:search",
    "run:create", "run:read", "run:cancel",
    "chat:send", "chat:read", "chat:delete",
    "persona:create", "persona:read", "persona:update", "persona:delete",
    "provider:create", "provider:read", "provider:update", "provider:delete",
    "mcp_provider:create", "mcp_provider:read", "mcp_provider:update", "mcp_provider:delete", "mcp_provider:sync",
    "mcp_tool:read", "mcp_tool:sync",
    "datasource:create", "datasource:read", "datasource:update", "datasource:delete", "datasource:sync",
    "schedule:create", "schedule:read", "schedule:update", "schedule:delete",
    "project:create", "project:read", "project:update", "project:delete",
    "web_search:manage", "web_search:test",
    "collection:create", "collection:read", "collection:update", "collection:delete", "collection:list",
    "document:create", "document:read", "document:update", "document:delete", "document:search",
    "graph:build", "graph:read", "graph:delete", "graph:search",
    "tool:read", "tool:execute",
]

ENDUSER_PERMISSIONS = [
    "user:read",
    "settings:read", "settings:update",
    "memory:create", "memory:read", "memory:update", "memory:delete",
    "api_key:create", "api_key:read", "api_key:update", "api_key:delete",
    "agent:read", "agent:list", "agent:invoke", "agent:stream",
    "assistant:read", "assistant:search",
    "thread:create", "thread:read", "thread:update", "thread:delete", "thread:search",
    "run:create", "run:read", "run:cancel",
    "chat:send", "chat:read", "chat:delete",
    "persona:read",
    "provider:read",
    "mcp_tool:read",
    "project:create", "project:read", "project:update", "project:delete",
    "tool:read", "tool:execute",
    "collection:read", "collection:list",
    "document:search",
    "graph:search",
]


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_permissions_service", "permissions", ["service"])
    op.create_index("ix_permissions_entity", "permissions", ["entity"])

    for perm in PERMISSIONS_SEED:
        is_system = "true" if perm.get("is_system") else "false"
        desc = perm.get("description") or f"Allows {perm['action']} operations on {perm['entity']}"
        op.execute(f"""INSERT INTO permissions (name, label, description, entity, service, action, is_system) VALUES ('{perm["name"]}', '{perm["label"]}', '{desc}', '{perm["entity"]}', '{perm["service"]}', '{perm["action"]}', {is_system})""")

    op.execute("""INSERT INTO roles (name, description, permissions, is_builtin) VALUES ('system-admin', 'System administrator with full access', '["*"]', true) ON CONFLICT (name) DO NOTHING""")

    enterprise_perms_json = str(ENTERPRISE_PERMISSIONS).replace("'", '"')
    op.execute(f"""INSERT INTO roles (name, description, permissions, is_builtin) VALUES ('enterprise-admin', 'Enterprise administrator with operational access', '{enterprise_perms_json}', true) ON CONFLICT (name) DO NOTHING""")

    enduser_perms_json = str(ENDUSER_PERMISSIONS).replace("'", '"')
    op.execute(f"""UPDATE roles SET permissions = '{enduser_perms_json}', description = 'Standard end user access with granular permissions' WHERE name = 'enduser'""")


def downgrade() -> None:
    op.execute("DELETE FROM permissions")
    op.drop_table("permissions")
    op.execute("DELETE FROM roles WHERE name IN ('system-admin', 'enterprise-admin')")
    op.execute("""UPDATE roles SET permissions = '["content:read"]', description = 'Standard end user access' WHERE name = 'enduser'""")
