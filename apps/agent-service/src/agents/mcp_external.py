"""Runtime loader for tools exposed by connected *external* MCP servers.

Complements ``agents.mcp_loader`` (which only knows the built-in tools service).
Each ``CONNECTED`` external provider is contacted with the acting user's stored
credentials; any provider whose auth is unavailable is skipped, never fatal.
"""

from __future__ import annotations

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from core.env import env
from core.logger import get_logger
from service.MCPCredentialService import MCPAuthError, MCPCredentialService
from service.MCPToolService import qualify_mcp_tool_name
from service.persistence_gateway import (
    mcp_provider_repository_class,
    mcp_tool_repository_class,
)

# Bound as module attributes on purpose: the loader constructs them per call
# and tests substitute them by patching these names.
MCPProviderRepository = mcp_provider_repository_class()
MCPToolRepository = mcp_tool_repository_class()

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
    except Exception as exc:  # noqa: BLE001 - DB unreachable etc.
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
            headers = await MCPCredentialService.get_instance().resolve_headers(
                provider, user_id=user_id
            )
        except MCPAuthError as exc:
            logger.info(
                "external MCP %s: auth unavailable, skipping (%s)", provider.get("name"), exc
            )
            continue

        conn: dict[str, Any] = {
            "transport": "sse"
            if str(provider.get("transport", "")).lower() == "sse"
            else "streamable_http",
            "url": provider["url"],
        }
        if headers:
            conn["headers"] = headers

        try:
            client = MultiServerMCPClient({f"ext-{provider['int_id']}": conn})
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001 - one bad server must not break the run
            logger.warning("external MCP %s: connect/list failed: %s", provider.get("name"), exc)
            continue

        for tool in tools:
            qualified = qualify_mcp_tool_name(provider, tool.name)
            if qualified in out:
                logger.warning(
                    "external MCP qualified tool collision on %r; keeping first", qualified
                )
                continue
            try:
                out[qualified] = tool.model_copy(update={"name": qualified})
            except Exception:  # noqa: BLE001 - fall back to mutating .name
                tool.name = qualified
                out[qualified] = tool

    return out
