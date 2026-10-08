"""Pure helpers for MCP admin routes.

Extracted from ``admin_mcp_route`` and ``mcp_server_admin_route`` to share DTO
transformations, id conversions, and credential encryption across MCP admin
endpoints.
"""

from __future__ import annotations

import hashlib
from typing import Any

from error_contract import NotFoundError

from core.observability.logger import get_logger

logger = get_logger(__name__)
SECRET_CONFIG_KEYS = ("api_token", "oauth_client_secret", "admin_credentials")
VALID_STATUSES = {"CREATED", "AWAITING_AUTH", "FETCHING_TOOLS", "CONNECTED", "DISCONNECTED"}


def numeric_id_for(provider_id: str) -> int:
    """Derive a stable positive integer id from a provider UUID.

    48 bits keeps the value well inside JavaScript's safe integer range while
    making collisions vanishingly unlikely for realistic provider counts.
    """
    digest = hashlib.blake2b(str(provider_id).encode("utf-8"), digest_size=6).digest()
    return int.from_bytes(digest, "big")


def server_config(provider: dict[str, Any]) -> dict[str, Any]:
    """Extract configuration dictionary from provider row."""
    config = provider.get("config")
    return config if isinstance(config, dict) else {}


def encrypt_mcp_secret(value: str) -> str | None:
    """Encrypt a secret, returning ``None`` when no encryption key is set."""
    try:
        from core.security.encryption import SecretScope, encrypt_secret

        return encrypt_secret(SecretScope.MCP_CREDENTIAL, value)
    except Exception as exc:
        logger.warning(f"MCP secret not stored — encryption unavailable: {exc}")
        return None


def to_mcp_server(provider: dict[str, Any], tool_count: int = 0) -> dict[str, Any]:
    """Render a provider row in the frontend's ``MCPServer`` shape."""
    config = server_config(provider)
    auth_type = config.get("auth_type", "NONE")
    is_authenticated = bool(auth_type == "NONE" or any(f"{k}_encrypted" in config for k in SECRET_CONFIG_KEYS))
    return {
        "id": provider["int_id"],
        "provider_id": provider["id"],
        "name": provider.get("name", ""),
        "description": provider.get("description") or "",
        "server_url": provider.get("url") or "",
        "owner": config.get("owner", "system"),
        "transport": provider.get("transport") or "streamable_http",
        "auth_type": auth_type,
        "auth_performer": config.get("auth_performer", "ADMIN"),
        "is_authenticated": is_authenticated,
        "user_authenticated": is_authenticated,
        "auth_template": config.get("auth_template"),
        "status": config.get("status", "CREATED"),
        "last_refreshed_at": config.get("last_refreshed_at"),
        "tool_count": tool_count,
    }


async def get_tool_count(tool_service: Any, provider_id: str) -> int:
    """Safely retrieve the tool count for a provider."""
    try:
        tools = await tool_service.list_tools_by_provider(provider_id)
        return len(tools)
    except Exception as exc:
        logger.warning(f"Failed to fetch tools for MCP provider {provider_id}: {exc}")
        return 0


async def resolve_mcp_provider(provider_service: Any, server_id: str) -> dict[str, Any]:
    """Resolve a provider by either UUID or int_id. Raises 404 if not found."""
    provider = await provider_service.resolve_provider(server_id)
    if not provider:
        raise NotFoundError(message_key="mcp_provider.not_found", message_params={"provider_id": server_id})
    return provider
