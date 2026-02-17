"""
MCP Server with HTTP transport for Open Agent Platform.
Uses FastMCP for simple tool definitions with modular plugin architecture.
Provides tools for web search, calculations, utilities, and more.
"""

import os
import sys
from pathlib import Path

from fastmcp import FastMCP

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.core.registry import ToolRegistry
from src.core.database import close_db_pool


# Initialize FastMCP server
mcp = FastMCP("open-agent-tools")

# Initialize the tool registry with plugin discovery
registry = ToolRegistry(mcp)

# Discover and register all tool categories from src/tools/
plugins_dir = Path(__file__).parent / "src" / "tools"
registry.discover_plugins(str(plugins_dir))


# Cleanup hook for graceful shutdown
async def cleanup():
    """Cleanup resources on shutdown."""
    await registry.cleanup_all()
    await close_db_pool()


# Run with HTTP transport for Open Agent Platform compatibility
if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", 8001))
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    
    print(f"\n{'='*60}")
    print(f"MCP Server - Modular Architecture")
    print(f"{'='*60}")
    print(f"Starting FastMCP Server on http://{host}:{port}")
    print(f"MCP endpoint: http://{host}:{port}/mcp")
    print(f"{'='*60}\n")
    
    # Use HTTP transport (serves at /mcp endpoint)
    mcp.run(transport="http", host=host, port=port)
