from __future__ import annotations

from config_manager import env
from error_contract import ConfigurationError

from core.observability.logger import get_logger
from core.security.mcp.mcp_url_policy import default_mcp_url
from schemas.proxy import (
    ProxyExecuteToolResponse,
    ProxyOllamaModelsResponse,
    ProxyRagCollectionsResponse,
    ProxyToolsResponse,
)
from service.proxy import ProxyService, get_proxy_service

logger = get_logger(__name__)


def _get_service() -> ProxyService:
    """Get the singleton ProxyService instance."""
    return get_proxy_service()


async def get_mcp_tools() -> ProxyToolsResponse:
    """
    Get list of available MCP tools from the platform's own MCP server.
    Used by the UI to populate tool selection for pipeline stages.

    The target is server-side configuration, not a caller-supplied query
    parameter: accepting one meant INTERNAL_SERVICE_TOKEN was attached
    (see ProxyService._mcp_connection) to whatever host the caller
    named.
    """
    tools_service_url = default_mcp_url()
    service = _get_service()
    return await service.get_mcp_tools(tools_service_url)


async def get_ollama_models() -> ProxyOllamaModelsResponse:
    """
    Get list of available Ollama models.
    Fetches from Ollama API at OLLAMA_BASE_URL.
    """
    ollama_url = env.OLLAMA_BASE_URL
    if not ollama_url:
        raise ConfigurationError()
    service = _get_service()
    return await service.get_ollama_models(ollama_url, env.OLLAMA_MODEL)


async def get_rag_collections(access_token: str) -> ProxyRagCollectionsResponse:
    """Proxy endpoint to get RAG collections from rag-service."""
    service = _get_service()
    return await service.get_rag_collections(access_token=access_token)


async def get_builtin_mcp_tools() -> ProxyToolsResponse:
    """
    Get list of available MCP tools from the built-in tools-service.
    Uses the configured internal tools-service URL.
    """
    tools_service_url = default_mcp_url()
    service = _get_service()
    return await service.get_builtin_mcp_tools(tools_service_url)


async def execute_mcp_tool(tool_name: str, arguments: dict | None) -> ProxyExecuteToolResponse:
    """
    Execute a tool on the platform's own MCP server and return the result.

    The target is server-side configuration, not a caller-supplied query
    parameter -- see the identical note on get_mcp_tools above.
    """
    if arguments is None:
        arguments = {}
    tools_service_url = default_mcp_url()
    service = _get_service()
    return await service.execute_mcp_tool(tool_name, arguments, tools_service_url)
