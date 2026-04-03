"""
Proxy routes for external services.

Endpoints:
  GET /mcp/tools    — list MCP tools from the MCP server
  GET /ollama/models — list available Ollama models
  GET /rag/collections — list RAG collections from langconnect-api
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, Query

from core import settings
from service.AuthService import verify_bearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["proxy"], dependencies=[Depends(verify_bearer)])


@router.get("/mcp/tools")
async def get_mcp_tools(
    url: str = Query(
        default="http://mcp-server:8002/mcp",
        description="MCP Server URL",
    ),
) -> dict:
    """
    Get list of available MCP tools from the specified MCP server.
    Used by the UI to populate tool selection for pipeline stages.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(
            connections={
                "mcp-tools": {
                    "transport": "streamable_http",
                    "url": url,
                }
            }
        )

        tools = await client.get_tools()

        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                }
                for tool in tools
            ]
        }
    except Exception as e:
        logger.error(f"Failed to fetch MCP tools: {e}")
        return {"tools": [], "error": str(e)}


@router.get("/ollama/models")
async def get_ollama_models() -> dict:
    """
    Get list of available Ollama models.
    Fetches from Ollama API at OLLAMA_BASE_URL.
    """
    ollama_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{ollama_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"models": models, "default": settings.OLLAMA_MODEL}
            else:
                return {
                    "models": [settings.OLLAMA_MODEL],
                    "default": settings.OLLAMA_MODEL,
                    "error": "Could not fetch models",
                }
    except Exception as e:
        logger.warning(f"Could not fetch Ollama models: {e}")
        return {
            "models": [settings.OLLAMA_MODEL],
            "default": settings.OLLAMA_MODEL,
            "error": str(e),
        }


@router.get("/rag/collections")
async def get_rag_collections() -> dict:
    """Proxy endpoint to get RAG collections from langconnect-api."""
    rag_api_url = os.environ.get("RAG_API_URL", "http://langconnect-api:8080")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{rag_api_url}/collections")
            if response.status_code == 200:
                return response.json()
            else:
                return {"collections": [], "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.warning(f"Could not fetch RAG collections: {e}")
        return {"collections": [], "error": str(e)}
