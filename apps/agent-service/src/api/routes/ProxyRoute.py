"""
Proxy routes for external services.

Endpoints:
  GET /mcp/tools    — list MCP tools from the MCP server
  GET /mcp/tools-builtin — list tools from built-in tools-service
  POST /mcp/execute — execute a tool on the MCP server
  GET /ollama/models — list available Ollama models
  GET /rag/collections — list RAG collections from langconnect-api
"""

import logging
import os

from fastapi import APIRouter, Body, Depends, Query

from api.dependencies import require_user
from controller import ProxyController, get_proxy_controller
from core import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"], dependencies=[Depends(require_user)])


def _get_controller() -> ProxyController:
    """Get the singleton ProxyController instance."""
    return get_proxy_controller()


@router.get("/mcp/tools")
async def get_mcp_tools(
    url: str = Query(
        default="http://tools-service:8003/mcp",
        description="MCP Server URL",
    ),
) -> dict:
    """
    Get list of available MCP tools from the specified MCP server.
    Used by the UI to populate tool selection for pipeline stages.
    """
    ctrl = _get_controller()
    return await ctrl.get_mcp_tools(url)


@router.get("/ollama/models")
async def get_ollama_models() -> dict:
    """
    Get list of available Ollama models.
    Fetches from Ollama API at OLLAMA_BASE_URL.
    """
    ollama_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"
    ctrl = _get_controller()
    return await ctrl.get_ollama_models(ollama_url, settings.OLLAMA_MODEL)


@router.get("/rag/collections")
async def get_rag_collections() -> dict:
    """Proxy endpoint to get RAG collections from langconnect-api."""
    rag_api_url = os.environ.get("RAG_API_URL", "http://langconnect-api:8080")
    ctrl = _get_controller()
    return await ctrl.get_rag_collections(rag_api_url)


@router.get("/mcp/tools-builtin")
async def get_builtin_mcp_tools() -> dict:
    """
    Get list of available MCP tools from the built-in tools-service.
    Uses TOOLS_SERVICE_URL from settings (default: http://localhost:8003/mcp).
    """
    tools_service_url = getattr(settings, "TOOLS_SERVICE_URL", None) or settings.MCP_SERVER_URL
    ctrl = _get_controller()
    return await ctrl.get_builtin_mcp_tools(tools_service_url)


@router.post("/mcp/execute")
async def execute_mcp_tool(
    tool_name: str = Body(..., description="Name of the tool to execute"),
    arguments: dict = Body(default={}, description="Arguments to pass to the tool"),
    url: str = Query(
        default=None,
        description="MCP Server URL (optional, defaults to TOOLS_SERVICE_URL)",
    ),
) -> dict:
    """
    Execute a tool on the MCP server and return the result.
    Uses TOOLS_SERVICE_URL from settings if no URL is provided.
    """
    # Use TOOLS_SERVICE_URL as default if no URL provided
    if url is None:
        tools_service_url = getattr(settings, "TOOLS_SERVICE_URL", None) or settings.MCP_SERVER_URL
        url = tools_service_url

    ctrl = _get_controller()
    return await ctrl.execute_mcp_tool(tool_name, arguments, url)
