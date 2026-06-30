"""add additional permissions for analyst, operator, rag-manager personas

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ADDITIONAL_PERMISSIONS = [
    {
        "name": "group:create",
        "label": "Create Groups",
        "entity": "group",
        "service": "user-service",
        "action": "create",
    },
    {
        "name": "group:read",
        "label": "Read Groups",
        "entity": "group",
        "service": "user-service",
        "action": "read",
    },
    {
        "name": "group:update",
        "label": "Update Groups",
        "entity": "group",
        "service": "user-service",
        "action": "update",
    },
    {
        "name": "group:delete",
        "label": "Delete Groups",
        "entity": "group",
        "service": "user-service",
        "action": "delete",
    },
    {
        "name": "group:list",
        "label": "List Groups",
        "entity": "group",
        "service": "user-service",
        "action": "list",
    },
    {
        "name": "group:manage",
        "label": "Manage Groups",
        "entity": "group",
        "service": "user-service",
        "action": "manage",
    },
    {
        "name": "analytics:read",
        "label": "Read Analytics",
        "entity": "analytics",
        "service": "agent-service",
        "action": "read",
    },
    {
        "name": "analytics:export",
        "label": "Export Analytics",
        "entity": "analytics",
        "service": "agent-service",
        "action": "export",
    },
    {
        "name": "conversation:read",
        "label": "Read Conversations",
        "entity": "conversation",
        "service": "agent-service",
        "action": "read",
    },
    {
        "name": "conversation:export",
        "label": "Export Conversations",
        "entity": "conversation",
        "service": "agent-service",
        "action": "export",
    },
    {
        "name": "conversation:delete",
        "label": "Delete Conversations",
        "entity": "conversation",
        "service": "agent-service",
        "action": "delete",
    },
    {
        "name": "monitor:read",
        "label": "Read System Monitoring",
        "entity": "monitor",
        "service": "system",
        "action": "read",
    },
    {
        "name": "monitor:alert",
        "label": "Manage Alerts",
        "entity": "monitor",
        "service": "system",
        "action": "alert",
    },
    {
        "name": "chunk:read",
        "label": "Read Document Chunks",
        "entity": "chunk",
        "service": "rag-service",
        "action": "read",
    },
    {
        "name": "chunk:search",
        "label": "Search Document Chunks",
        "entity": "chunk",
        "service": "rag-service",
        "action": "search",
    },
    {
        "name": "embedding:read",
        "label": "View Embeddings",
        "entity": "embedding",
        "service": "rag-service",
        "action": "read",
    },
    {
        "name": "agent:assign",
        "label": "Assign Agents to Users",
        "entity": "agent",
        "service": "agent-service",
        "action": "assign",
    },
    {
        "name": "agent:share",
        "label": "Share Agents",
        "entity": "agent",
        "service": "agent-service",
        "action": "share",
    },
    {
        "name": "audit_log:manage",
        "label": "Manage Audit Logs",
        "entity": "audit_log",
        "service": "user-service",
        "action": "manage",
        "is_system": True,
    },
]

# enterprise-admin full permission list: 0006 base + new additions
ENTERPRISE_ADMIN_PERMISSIONS = [
    "agent:assign",
    "agent:create",
    "agent:delete",
    "agent:list",
    "agent:read",
    "agent:share",
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
    "audit_log:export",
    "audit_log:list",
    "audit_log:manage",
    "audit_log:read",
    "chat:delete",
    "chat:read",
    "chat:send",
    "chunk:read",
    "chunk:search",
    "collection:create",
    "collection:delete",
    "collection:list",
    "collection:read",
    "collection:update",
    "conversation:delete",
    "conversation:export",
    "conversation:read",
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
    "group:create",
    "group:delete",
    "group:list",
    "group:manage",
    "group:read",
    "group:update",
    "mcp_provider:create",
    "mcp_provider:delete",
    "mcp_provider:read",
    "mcp_provider:sync",
    "mcp_provider:update",
    "mcp_tool:read",
    "mcp_tool:sync",
    "monitor:alert",
    "monitor:read",
    "permission:list",
    "permission:read",
    "persona:create",
    "persona:delete",
    "persona:read",
    "persona:update",
    "project:create",
    "project:delete",
    "project:read",
    "project:update",
    "provider:create",
    "provider:delete",
    "provider:read",
    "provider:update",
    "role:list",
    "role:read",
    "run:cancel",
    "run:create",
    "run:read",
    "schedule:create",
    "schedule:delete",
    "schedule:read",
    "schedule:update",
    "settings:read",
    "settings:update",
    "thread:create",
    "thread:delete",
    "thread:read",
    "thread:search",
    "thread:update",
    "tool:execute",
    "tool:read",
    "user:create",
    "user:delete",
    "user:list",
    "user:read",
    "user:update",
    "web_search:manage",
    "web_search:test",
]

# enduser full permission list: 0006 base + new additions
ENDUSER_PERMISSIONS = [
    "agent:invoke",
    "agent:list",
    "agent:read",
    "agent:stream",
    "api_key:create",
    "api_key:delete",
    "api_key:read",
    "api_key:update",
    "assistant:read",
    "assistant:search",
    "chat:delete",
    "chat:read",
    "chat:send",
    "chunk:read",
    "chunk:search",
    "collection:list",
    "collection:read",
    "conversation:export",
    "datasource:read",
    "document:read",
    "document:search",
    "graph:read",
    "graph:search",
    "mcp_provider:read",
    "mcp_tool:read",
    "memory:create",
    "memory:delete",
    "memory:read",
    "memory:update",
    "persona:read",
    "project:create",
    "project:delete",
    "project:read",
    "project:update",
    "provider:read",
    "run:cancel",
    "run:create",
    "run:read",
    "settings:read",
    "settings:update",
    "thread:create",
    "thread:delete",
    "thread:read",
    "thread:search",
    "thread:update",
    "tool:execute",
    "tool:read",
    "user:read",
]

# Original 0006 permission lists for downgrade
_0006_ENTERPRISE_ADMIN_PERMISSIONS = [
    "agent:create",
    "agent:delete",
    "agent:list",
    "agent:read",
    "agent:update",
    "agent_definition:create",
    "agent_definition:delete",
    "agent_definition:read",
    "agent_definition:update",
    "assistant:create",
    "assistant:delete",
    "assistant:read",
    "assistant:search",
    "assistant:update",
    "audit_log:export",
    "audit_log:list",
    "audit_log:read",
    "chat:delete",
    "chat:read",
    "chat:send",
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
    "graph:build",
    "graph:delete",
    "graph:read",
    "graph:search",
    "mcp_provider:create",
    "mcp_provider:delete",
    "mcp_provider:read",
    "mcp_provider:sync",
    "mcp_provider:update",
    "mcp_tool:read",
    "mcp_tool:sync",
    "permission:list",
    "permission:read",
    "persona:create",
    "persona:delete",
    "persona:read",
    "persona:update",
    "project:create",
    "project:delete",
    "project:read",
    "project:update",
    "provider:create",
    "provider:delete",
    "provider:read",
    "provider:update",
    "role:list",
    "role:read",
    "run:cancel",
    "run:create",
    "run:read",
    "schedule:create",
    "schedule:delete",
    "schedule:read",
    "schedule:update",
    "settings:read",
    "settings:update",
    "thread:create",
    "thread:delete",
    "thread:read",
    "thread:search",
    "thread:update",
    "tool:execute",
    "tool:read",
    "user:create",
    "user:delete",
    "user:list",
    "user:read",
    "user:update",
    "web_search:manage",
    "web_search:test",
]

_0006_ENDUSER_PERMISSIONS = [
    "agent:invoke",
    "agent:list",
    "agent:read",
    "agent:stream",
    "api_key:create",
    "api_key:delete",
    "api_key:read",
    "api_key:update",
    "assistant:read",
    "assistant:search",
    "chat:delete",
    "chat:read",
    "chat:send",
    "collection:list",
    "collection:read",
    "document:search",
    "graph:search",
    "mcp_tool:read",
    "memory:create",
    "memory:delete",
    "memory:read",
    "memory:update",
    "persona:read",
    "project:create",
    "project:delete",
    "project:read",
    "project:update",
    "provider:read",
    "run:cancel",
    "run:create",
    "run:read",
    "settings:read",
    "settings:update",
    "thread:create",
    "thread:delete",
    "thread:read",
    "thread:search",
    "thread:update",
    "tool:execute",
    "tool:read",
    "user:read",
]


def upgrade() -> None:
    conn = op.get_bind()

    existing = {row[0] for row in conn.execute(sa.text("SELECT name FROM permissions")).fetchall()}

    added = 0
    for perm in ADDITIONAL_PERMISSIONS:
        if perm["name"] in existing:
            continue
        desc = perm.get("description") or f"Allows {perm['action']} on {perm['entity']}"
        conn.execute(
            sa.text(
                """INSERT INTO permissions (name, label, description, entity, service, action, is_system)
                    VALUES (:name, :label, :description, :entity, :service, :action, :is_system)"""
            ).bindparams(
                name=perm["name"],
                label=perm["label"],
                description=desc,
                entity=perm["entity"],
                service=perm["service"],
                action=perm["action"],
                is_system=bool(perm.get("is_system")),
            )
        )
        added += 1

    print(f"Migration 0009: added {added} new permissions")

    import json

    ea_json = json.dumps(sorted(ENTERPRISE_ADMIN_PERMISSIONS))
    op.execute(f"UPDATE roles SET permissions = '{ea_json}' WHERE name = 'enterprise-admin'")
    eu_json = json.dumps(sorted(ENDUSER_PERMISSIONS))
    op.execute(f"UPDATE roles SET permissions = '{eu_json}' WHERE name = 'enduser'")
    print("Migration 0009: updated built-in role permission lists")


def downgrade() -> None:
    conn = op.get_bind()
    new_names = [perm["name"] for perm in ADDITIONAL_PERMISSIONS]

    for name in new_names:
        conn.execute(sa.text("DELETE FROM permissions WHERE name = :name").bindparams(name=name))

    import json

    ea_json = json.dumps(sorted(_0006_ENTERPRISE_ADMIN_PERMISSIONS))
    op.execute(f"UPDATE roles SET permissions = '{ea_json}' WHERE name = 'enterprise-admin'")
    eu_json = json.dumps(sorted(_0006_ENDUSER_PERMISSIONS))
    op.execute(f"UPDATE roles SET permissions = '{eu_json}' WHERE name = 'enduser'")
