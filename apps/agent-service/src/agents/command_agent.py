"""Command Agent - executes deterministic commands via MCP."""

import logging
from datetime import datetime
from typing import List, Optional

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from langgraph.graph.state import CompiledStateGraph

from agents.lazy_agent import LazyLoadingAgent
from core import get_model, settings

logger = logging.getLogger(__name__)

current_date = datetime.now().strftime("%B %d, %Y")
SYSTEM_PROMPT = f"""You are a Command execution agent.
Your primary role is to execute deterministic commands using the provided tools.
You have access to shell execution, Docker management, and file operations.
Today's date is {current_date}.

Security Guidelines:
- Only execute commands that are explicitly requested.
- If Sandbox Mode is enabled (default), dangerous commands (rm -rf /, etc.) are blocked by the tool.
- Respect the allowed commands list provided in your configuration.
"""

class CommandAgent(LazyLoadingAgent):
    """Command Agent with async initialization for MCP tools."""
    
    def __init__(self) -> None:
        super().__init__()
        self._mcp_tools: List[BaseTool] = []
        self._mcp_client: MultiServerMCPClient | None = None

    async def load(self) -> None:
        """Initialize the agent by loading MCP tools."""
        try:
             # MCP connection details
            mcp_url = settings.MCP_SERVER_URL
            
            connections = {
                "command-server": StreamableHttpConnection(
                    transport="streamable_http",
                    url=mcp_url,
                )
            }

            self._mcp_client = MultiServerMCPClient(connections)
            logger.info(f"Connecting to MCP server at {mcp_url}")

            # Get tools
            self._mcp_tools = await self._mcp_client.get_tools()
            logger.info(f"Command agent loaded with {len(self._mcp_tools)} tools")

        except Exception as e:
            logger.error(f"Failed to initialize Command agent: {e}")
            self._mcp_tools = []

        self._graph = self._create_graph()
        self._loaded = True

    def _create_graph(self) -> CompiledStateGraph:
        model = get_model(settings.DEFAULT_MODEL)

        return create_agent(
            model=model,
            tools=self._mcp_tools,
            name="command-agent",
            system_prompt=SYSTEM_PROMPT,
        )

command_agent = CommandAgent()
