"""Runtime loader for tools exposed by connected *external* MCP servers.

Complements ``agents.tooling.mcp_loader`` (which only knows the built-in tools service).
Each ``CONNECTED`` external provider is contacted with the acting user's stored
credentials; any provider whose auth is unavailable is skipped, never fatal.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config_manager import env
from langchain_mcp_adapters.client import MultiServerMCPClient

from core.observability.logger import get_logger
from core.security.mcp.mcp_ssrf_guard import MCPUrlRejected, validate_mcp_server_url
from infrastructure.db.persistence_gateway import (
    mcp_provider_repository_class,
    mcp_tool_repository_class,
)
from service.mcp.mcp_credential_service import MCPAuthError, MCPCredentialService
from service.mcp.mcp_tool_service import qualify_mcp_tool_name

# Bound as module attributes on purpose: the loader constructs them per call
# and tests substitute them by patching these names.
MCPProviderRepository = mcp_provider_repository_class()
MCPToolRepository = mcp_tool_repository_class()

# Matches configurable_mcp_agent.py's MCP_TOOL_FETCH_TIMEOUT_SECONDS for the
# built-in tool loader. Without this, an unresponsive CONNECTED provider hung
# the caller indefinitely -- agent load for DynamicAgent, or a turn's graph
# build on a cache miss for ConfigurableMCPAgent.
EXTERNAL_MCP_TOOL_FETCH_TIMEOUT_SECONDS = 20.0

logger = get_logger(__name__)


async def load_external_mcp_tools(
    user_id: str | None,
    wanted_names: set[str] | None = None,
) -> dict[str, Any]:
    """Return ``{qualified_tool_name: BaseTool}`` for every reachable external server.

    Keys are the server-scoped qualified name (``<slug>__<tool>``) so tools with
    the same raw name on different servers stay distinct; each returned tool's
    ``.name`` is set to that qualified name too, so the LLM calls it correctly.

    ``wanted_names`` (qualified) skips any provider whose cached tools do not
    intersect it, so an agent that references three tools does not open
    connections to unrelated servers.
    """
    if not env.MCP_EXTERNAL_ENABLED:
        return {}

    provider_repo = MCPProviderRepository()
    tool_repo = MCPToolRepository()

    try:
        providers = await provider_repo.list_all(include_inactive=False)
    except Exception as exc:
        logger.warning("external MCP: could not list providers: %s", exc)
        return {}

    out: dict[str, Any] = {}
    for provider in providers:
        if (
            provider.get("type") != "external"
            or provider.get("server_status") != "CONNECTED"
            or not provider.get("url")
        ):
            continue

        if wanted_names is not None:
            cached = await tool_repo.list_by_provider(provider["id"], include_inactive=False)
            cached_qualified = {qualify_mcp_tool_name(provider, t["name"]) for t in cached}
            if cached_qualified.isdisjoint(wanted_names):
                continue

        try:
            headers = await MCPCredentialService.get_instance().resolve_headers(provider, user_id=user_id)
        except MCPAuthError as exc:
            logger.info("external MCP %s: auth unavailable, skipping (%s)", provider.get("name"), exc)
            continue

        # Re-checked here and not only at registration time: the row was
        # validated when an admin saved it, but a name can start resolving
        # somewhere else afterwards (DNS rebinding, or a simply changed
        # record), and resolve_headers above has already put the stored
        # credentials in hand.
        try:
            await validate_mcp_server_url(provider["url"])
        except MCPUrlRejected as exc:
            logger.warning(
                "external MCP %s: refusing to connect to %s (%s)",
                provider.get("name"),
                provider.get("url"),
                exc.message,
            )
            continue

        conn: dict[str, Any] = {
            "transport": "sse" if str(provider.get("transport", "")).lower() == "sse" else "streamable_http",
            "url": provider["url"],
        }
        if headers:
            conn["headers"] = headers

        try:
            client = MultiServerMCPClient({f"ext-{provider['int_id']}": conn})
            tools = await asyncio.wait_for(client.get_tools(), timeout=EXTERNAL_MCP_TOOL_FETCH_TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning("external MCP %s: connect/list failed: %s", provider.get("name"), exc)
            continue

        for tool in tools:
            qualified = qualify_mcp_tool_name(provider, tool.name)
            if qualified in out:
                logger.warning("external MCP qualified tool collision on %r; keeping first", qualified)
                continue
            try:
                out[qualified] = tool.model_copy(update={"name": qualified})
            except Exception:
                tool.name = qualified
                out[qualified] = tool

    return out
