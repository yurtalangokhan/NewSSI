"""Permission catalog owned by agent-service."""

from __future__ import annotations

from typing import TypedDict


class PermissionDefinition(TypedDict, total=False):
    name: str
    label: str
    description: str | None
    entity: str
    service: str
    action: str
    is_system: bool


SERVICE_NAME = "agent-service"


def _permission(entity: str, action: str, label: str) -> PermissionDefinition:
    return {
        "name": f"{entity}:{action}",
        "label": label,
        "description": None,
        "entity": entity,
        "service": SERVICE_NAME,
        "action": action,
        "is_system": False,
    }


SERVICE_PERMISSIONS: list[PermissionDefinition] = [
    _permission("agent", "assign", "Assign Agents to Users"),
    _permission("agent", "create", "Create Agents"),
    _permission("agent", "delete", "Delete Agents"),
    _permission("agent", "invoke", "Invoke Agents"),
    _permission("agent", "list", "List Agents"),
    _permission("agent", "read", "Read Agents"),
    _permission("agent", "share", "Share Agents"),
    _permission("agent", "stream", "Stream Agents"),
    _permission("agent", "update", "Update Agents"),
    _permission("agent_definition", "create", "Create Agent Definitions"),
    _permission("agent_definition", "delete", "Delete Agent Definitions"),
    _permission("agent_definition", "read", "Read Agent Definitions"),
    _permission("agent_definition", "update", "Update Agent Definitions"),
    _permission("analytics", "export", "Export Analytics"),
    _permission("analytics", "read", "Read Analytics"),
    _permission("assistant", "create", "Create Assistants"),
    _permission("assistant", "delete", "Delete Assistants"),
    _permission("assistant", "read", "Read Assistants"),
    _permission("assistant", "search", "Search Assistants"),
    _permission("assistant", "update", "Update Assistants"),
    _permission("chat", "delete", "Delete Chat Messages"),
    _permission("chat", "read", "Read Chat Messages"),
    _permission("chat", "send", "Send Chat Messages"),
    _permission("conversation", "delete", "Delete Conversations"),
    _permission("conversation", "export", "Export Conversations"),
    _permission("conversation", "read", "Read Conversations"),
    _permission("datasource", "create", "Create Datasources"),
    _permission("datasource", "delete", "Delete Datasources"),
    _permission("datasource", "read", "Read Datasources"),
    _permission("datasource", "sync", "Sync Datasources"),
    _permission("datasource", "update", "Update Datasources"),
    _permission("mcp_provider", "create", "Create MCP Providers"),
    _permission("mcp_provider", "delete", "Delete MCP Providers"),
    _permission("mcp_provider", "read", "Read MCP Providers"),
    _permission("mcp_provider", "sync", "Sync MCP Providers"),
    _permission("mcp_provider", "update", "Update MCP Providers"),
    _permission("mcp_tool", "read", "Read MCP Tools"),
    _permission("mcp_tool", "sync", "Sync MCP Tools"),
    _permission("persona", "create", "Create Personas"),
    _permission("persona", "delete", "Delete Personas"),
    _permission("persona", "read", "Read Personas"),
    _permission("persona", "update", "Update Personas"),
    _permission("project", "create", "Create Projects"),
    _permission("project", "delete", "Delete Projects"),
    _permission("project", "read", "Read Projects"),
    _permission("project", "update", "Update Projects"),
    _permission("provider", "create", "Create LLM Providers"),
    _permission("provider", "delete", "Delete LLM Providers"),
    _permission("provider", "read", "Read LLM Providers"),
    _permission("provider", "update", "Update LLM Providers"),
    _permission("run", "cancel", "Cancel Runs"),
    _permission("run", "create", "Create Runs"),
    _permission("run", "read", "Read Runs"),
    _permission("schedule", "create", "Create Schedules"),
    _permission("schedule", "delete", "Delete Schedules"),
    _permission("schedule", "read", "Read Schedules"),
    _permission("schedule", "update", "Update Schedules"),
    _permission("thread", "create", "Create Threads"),
    _permission("thread", "delete", "Delete Threads"),
    _permission("thread", "read", "Read Threads"),
    _permission("thread", "search", "Search Threads"),
    _permission("thread", "update", "Update Threads"),
    _permission("web_search", "manage", "Manage Web Search Providers"),
    _permission("web_search", "test", "Test Web Search"),
]


def list_service_permissions() -> list[PermissionDefinition]:
    """Return the permission catalog owned by agent-service."""
    return list(SERVICE_PERMISSIONS)
