"""Shared MCP tool loader for DynamicAgent and FlowAgent."""

from __future__ import annotations

from typing import Any

from core import settings
from core.env import env
from core.logger import get_logger

logger = get_logger(__name__)


async def load_mcp_tools_map(
    agent_name: str = "agent",
    *,
    user_id: str | None = None,
    wanted_names: set[str] | None = None,
) -> dict[str, Any]:
    """Load all available MCP tools into a dictionary keyed by tool name.

    Built-in tool-service tools load first; tools from connected external MCP
    servers (resolved with ``user_id``'s stored credentials) are merged in
    afterwards and never override a built-in of the same name.
    """
    tools_map: dict[str, Any] = {}
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        mcp_url = (
            getattr(settings, "TOOLS_SERVICE_URL", None)
            or getattr(settings, "MCP_SERVER_URL", None)
            or env.TOOLS_SERVICE_URL
            or env.MCP_SERVER_URL
            or "http://localhost:8003/mcp"
        )
        token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else None

        client = MultiServerMCPClient(
            connections={
                "mcp-tools": {
                    "transport": "streamable_http",
                    "url": mcp_url,
                    **({"headers": headers} if headers else {}),
                }
            }
        )

        tools = await client.get_tools()
        for tool in tools:
            tools_map[tool.name] = tool

        logger.info(
            "Loaded %d MCP tools for '%s' from %s",
            len(tools),
            agent_name,
            mcp_url,
        )
    except Exception as e:
        logger.warning("Could not load MCP tools for '%s': %s", agent_name, e)

    try:
        from agents.mcp_external import load_external_mcp_tools

        external = await load_external_mcp_tools(user_id, wanted_names)
        for name, tool in external.items():
            tools_map.setdefault(name, tool)
        if external:
            logger.info("Merged %d external MCP tools for '%s'", len(external), agent_name)
    except Exception as e:  # noqa: BLE001 - external servers must not break the run
        logger.warning("Could not load external MCP tools for '%s': %s", agent_name, e)

    return tools_map
