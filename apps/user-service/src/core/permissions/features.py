"""Central product-feature taxonomy for the permission catalog.

Maps ``(service, entity)`` to a product feature so the web admin UI and any
client can group permissions by user-facing capability instead of by backend
service. Features intentionally span service boundaries (for example the
``tools`` feature mixes tools-service and agent-service entities).

The map is the single source of truth for the ``feature`` value stamped on
every permission during the permission sync.
"""

from typing import Final

FEATURE_LABELS: Final[dict[str, str]] = {
    "access": "Users & Access",
    "agents": "Agents & Assistants",
    "chat": "Chat & Conversations",
    "knowledge": "Knowledge & RAG",
    "tools": "Tools & Integrations",
    "workspace": "Workspace & Projects",
    "system": "System Administration",
}

FEATURE_MAP: Final[dict[tuple[str, str], str]] = {
    # access
    ("user-service", "user"): "access",
    ("user-service", "role"): "access",
    ("user-service", "permission"): "access",
    ("user-service", "api_key"): "access",
    ("user-service", "group"): "access",
    ("user-service", "audit_log"): "access",
    # agents
    ("agent-service", "agent"): "agents",
    ("agent-service", "agent_definition"): "agents",
    ("agent-service", "assistant"): "agents",
    ("agent-service", "persona"): "agents",
    # chat
    ("agent-service", "chat"): "chat",
    ("agent-service", "conversation"): "chat",
    ("agent-service", "thread"): "chat",
    ("agent-service", "run"): "chat",
    # knowledge
    ("rag-service", "collection"): "knowledge",
    ("rag-service", "document"): "knowledge",
    ("rag-service", "chunk"): "knowledge",
    ("rag-service", "embedding"): "knowledge",
    ("rag-service", "graph"): "knowledge",
    # tools
    ("tools-service", "tool"): "tools",
    ("agent-service", "mcp_provider"): "tools",
    ("agent-service", "mcp_tool"): "tools",
    ("agent-service", "mail_config"): "tools",
    ("agent-service", "datasource"): "tools",
    ("agent-service", "web_search"): "tools",
    ("agent-service", "provider"): "tools",
    ("agent-service", "schedule"): "tools",
    # workspace
    ("agent-service", "project"): "workspace",
    ("user-service", "memory"): "workspace",
    ("user-service", "settings"): "workspace",
    # system
    ("system", "system.settings"): "system",
    ("system", "monitor"): "system",
    ("agent-service", "analytics"): "system",
}

DEFAULT_FEATURE: Final[str] = "system"


def feature_for(service: str, entity: str) -> str:
    """Return the product feature for a service and entity pair.

    Unknown pairs fall back to the ``system`` feature so new entities always
    appear in the admin UI instead of disappearing from it.
    """
    return FEATURE_MAP.get((service, entity), DEFAULT_FEATURE)


def list_features() -> list[str]:
    """Return the ordered feature keys known to the taxonomy."""
    return list(FEATURE_LABELS)
