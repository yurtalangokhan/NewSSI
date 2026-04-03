"""MCP Perceptron - MCP server tool integration."""

import logging
import os
from typing import Any

from langchain_core.tools import BaseTool

from agents.base.perceptron import Perceptron, PerceptionResult

logger = logging.getLogger(__name__)


class MCPPerceptron(Perceptron):
    """
    Perceptron that loads and manages tools from MCP servers.

    MCP (Model Context Protocol) servers provide dynamic tools
    that can be loaded at runtime.
    """

    def __init__(
        self,
        mcp_servers: list[dict[str, str]] | None = None,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize MCP perceptron.

        Args:
            mcp_servers: List of MCP server configs
                [{"name": "server1", "url": "http://localhost:8000/mcp"}]
            config: Additional configuration
        """
        super().__init__(config)
        self._mcp_servers = mcp_servers or []
        self._mcp_client: Any = None

    @property
    def perceptron_type(self) -> str:
        return "mcp"

    async def load(self) -> None:
        """Load tools from MCP servers."""
        if not self._mcp_servers:
            # Try default server from settings
            mcp_url = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8002/mcp")
            self._mcp_servers = [{"name": "default", "url": mcp_url}]

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            connections = {}
            for server in self._mcp_servers:
                name = server.get("name", "mcp")
                url = server.get("url")
                transport = server.get("transport", "streamable_http")
                connections[name] = {
                    "transport": transport,
                    "url": url,
                }

            self._mcp_client = MultiServerMCPClient(connections=connections)
            tools = await self._mcp_client.get_tools()

            for tool in tools:
                self._tools[tool.name] = tool

            logger.info(f"Loaded {len(tools)} MCP tools: {list(self._tools.keys())}")

        except Exception as e:
            logger.warning(f"Failed to load MCP tools: {e}")
            self._mcp_client = None

    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """Process input - return MCP tools info."""
        return PerceptionResult(
            metadata={
                "available_mcp_tools": list(self._tools.keys()),
                "mcp_servers": [s.get("name") for s in self._mcp_servers],
            }
        )

    async def reload_tools(self, server_name: str | None = None) -> None:
        """
        Reload tools from MCP server(s).

        Args:
            server_name: Optional specific server to reload
        """
        if self._mcp_client:
            try:
                tools = await self._mcp_client.get_tools()
                if server_name:
                    # Reload specific server
                    pass
                else:
                    # Reload all
                    self._tools = {t.name: t for t in tools}
            except Exception as e:
                logger.error(f"Failed to reload MCP tools: {e}")

    def get_tools_by_capability(self, capability: str) -> list[BaseTool]:
        """
        Get tools that have a specific capability.

        This is a simple heuristic based on tool names.
        """
        capability_lower = capability.lower()
        return [tool for tool in self._tools.values() if capability_lower in tool.name.lower()]

    async def cleanup(self) -> None:
        """Cleanup MCP connections."""
        if self._mcp_client and hasattr(self._mcp_client, "cleanup"):
            try:
                await self._mcp_client.cleanup()
            except Exception as e:
                logger.error(f"Error during MCP cleanup: {e}")


class CompositePerceptron(Perceptron):
    """
    Composite perceptron that combines multiple perceptrons.

    Allows combining tool, memory, and MCP perceptrons into one.
    """

    def __init__(
        self,
        perceptrons: list[Perceptron] | None = None,
        config: dict[str, Any] | None = None,
    ):
        super().__init__(config)
        self._perceptrons: list[Perceptron] = perceptrons or []

    @property
    def perceptron_type(self) -> str:
        return "composite"

    @property
    def children(self) -> list[Perceptron]:
        """Get child perceptrons."""
        return self._perceptrons

    async def load(self) -> None:
        """Load all child perceptrons."""
        for p in self._perceptrons:
            await p.load()
            # Merge tools
            for tool in p.get_tools():
                self._tools[tool.name] = tool

    async def perceive(
        self,
        input: Any,
        context: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        """Process through all perceptrons."""
        results = []
        metadata = {"perceptrons": len(self._perceptrons)}

        for p in self._perceptrons:
            result = await p.perceive(input, context)
            results.append(result)
            metadata[f"{p.perceptron_type}_result"] = True

        return PerceptionResult(metadata=metadata)

    def add_perceptron(self, perceptron: Perceptron) -> None:
        """Add a child perceptron."""
        self._perceptrons.append(perceptron)

    def remove_perceptron(self, perceptron_type: str) -> None:
        """Remove a child perceptron by type."""
        self._perceptrons = [p for p in self._perceptrons if p.perceptron_type != perceptron_type]
