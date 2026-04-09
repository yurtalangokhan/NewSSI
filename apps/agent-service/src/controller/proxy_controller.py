"""Proxy controller - handles external service proxy logic (MCP, Ollama, RAG)."""

from typing import Any

from controller.base import BaseController


class ProxyController(BaseController):
    """Controller for proxy endpoints to external services.

    Handles MCP tool execution, Ollama model listing, and RAG collection proxying.
    """

    def __init__(self):
        pass

    # =========================================================================
    # MCP Tools
    # =========================================================================

    async def get_mcp_tools(self, url: str) -> dict[str, Any]:
        """Get list of available MCP tools from the specified MCP server."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(
                connections={
                    "mcp-tools": {
                        "transport": "streamable_http",
                        "url": self._ensure_mcp_url_path(url),
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
            return {"tools": [], "error": str(e)}

    async def get_builtin_mcp_tools(self, tools_service_url: str) -> dict[str, Any]:
        """Get list of available MCP tools from the built-in tools-service."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            import json

            client = MultiServerMCPClient(
                connections={
                    "tools-service": {
                        "transport": "streamable_http",
                        "url": self._ensure_mcp_url_path(tools_service_url),
                    }
                }
            )

            tools = await client.get_tools()

            def serialize_input_schema(schema: Any) -> dict[str, Any]:
                """Safely serialize input_schema to JSON-compatible dict."""
                import inspect

                if schema is None:
                    return {}
                # If it's already a dict, return it
                if isinstance(schema, dict):
                    return schema

                # Check if it's a class vs instance
                is_class = inspect.isclass(schema)

                # If it's a Pydantic model class, use model_json_schema()
                if is_class and hasattr(schema, "model_json_schema"):
                    try:
                        return schema.model_json_schema()
                    except Exception:
                        pass

                # If it's a Pydantic model instance, use model_dump()
                if not is_class and hasattr(schema, "model_dump"):
                    try:
                        return schema.model_dump()
                    except Exception:
                        pass

                # Try dict() for older Pydantic versions
                if hasattr(schema, "dict"):
                    try:
                        return schema.dict()
                    except Exception:
                        pass

                # If it has __dict__, use that
                if hasattr(schema, "__dict__"):
                    return dict(schema.__dict__)

                # Last resort: try to JSON serialize it
                try:
                    return json.loads(json.dumps(schema, default=str))
                except Exception:
                    return {}

            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": getattr(tool, "description", "") or "",
                        # Note: MCP SDK uses camelCase 'inputSchema', not snake_case
                        "input_schema": serialize_input_schema(getattr(tool, "inputSchema", None)),
                    }
                    for tool in tools
                ]
            }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error fetching builtin MCP tools: {e}")
            return {"tools": [], "error": str(e)}

    async def execute_mcp_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        url: str,
    ) -> dict[str, Any]:
        """Execute a tool on the MCP server and return the result."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(
                connections={
                    "mcp-tools": {
                        "transport": "streamable_http",
                        "url": self._ensure_mcp_url_path(url),
                    }
                }
            )

            tools = await client.get_tools()

            tool = next((t for t in tools if t.name == tool_name), None)
            if not tool:
                return {"error": f"Tool '{tool_name}' not found", "result": None}

            result = await client.arun(tool_name, arguments)

            return {"result": result, "error": None}
        except Exception as e:
            return {"result": None, "error": str(e)}

    # =========================================================================
    # Ollama
    # =========================================================================

    async def get_ollama_models(self, ollama_url: str, default_model: str) -> dict[str, Any]:
        """Get list of available Ollama models."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{ollama_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return {"models": models, "default": default_model}
                else:
                    return {
                        "models": [default_model],
                        "default": default_model,
                        "error": "Could not fetch models",
                    }
        except Exception as e:
            return {
                "models": [default_model],
                "default": default_model,
                "error": str(e),
            }

    # =========================================================================
    # RAG Collections
    # =========================================================================

    async def get_rag_collections(self, rag_api_url: str) -> dict[str, Any]:
        """Proxy endpoint to get RAG collections from langconnect-api."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{rag_api_url}/collections")
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"collections": [], "error": f"Status {response.status_code}"}
        except Exception as e:
            return {"collections": [], "error": str(e)}

    # =========================================================================
    # Helpers
    # =========================================================================

    def _ensure_mcp_url_path(self, url: str) -> str:
        """Ensure URL ends with /mcp path."""
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        path = parsed.path or ""
        if not path.endswith("/mcp"):
            path = path.rstrip("/") + "/mcp"
        return urlunparse(parsed._replace(path=path))


# Singleton instance
_proxy_controller: ProxyController | None = None


def get_proxy_controller() -> ProxyController:
    """Get the singleton ProxyController instance."""
    global _proxy_controller
    if _proxy_controller is None:
        _proxy_controller = ProxyController()
    return _proxy_controller
