"""Proxy controller - handles external service proxy logic (MCP, Ollama, RAG)."""

from typing import Any

from i18n import get_locale, t

from controller.base import BaseController
from core.env import env


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
                    "mcp-tools": self._mcp_connection(url),
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
            import json

            from langchain_mcp_adapters.client import MultiServerMCPClient

            def serialize_input_schema(schema: Any) -> dict[str, Any]:
                """Safely serialize input_schema to JSON-compatible dict."""
                import inspect

                if schema is None:
                    return {}
                if isinstance(schema, dict):
                    return schema

                is_class = inspect.isclass(schema)

                if is_class and hasattr(schema, "model_json_schema"):
                    try:
                        return schema.model_json_schema()
                    except Exception:
                        pass

                if not is_class and hasattr(schema, "model_dump"):
                    try:
                        return schema.model_dump()
                    except Exception:
                        pass

                if hasattr(schema, "dict"):
                    try:
                        return schema.dict()
                    except Exception:
                        pass

                if hasattr(schema, "__dict__"):
                    return dict(schema.__dict__)

                try:
                    return json.loads(json.dumps(schema, default=str))
                except Exception:
                    return {}

            def get_tool_schema(tool: Any) -> dict[str, Any]:
                if getattr(tool, "name", "") == "send_email":
                    return {
                        "type": "object",
                        "properties": {
                            "mail_config_id": {
                                "type": "string",
                                "title": "Mail config",
                                "description": "Select a saved SMTP mail config.",
                            },
                            "to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Recipient email addresses.",
                            },
                            "subject": {"type": "string"},
                            "body": {"type": "string", "widget": "textarea"},
                            "cc": {"type": "array", "items": {"type": "string"}},
                            "bcc": {"type": "array", "items": {"type": "string"}},
                            "is_html": {"type": "boolean", "default": False},
                            "reply_to": {"type": "string"},
                        },
                        "required": ["mail_config_id", "to", "subject", "body"],
                    }
                schema = getattr(tool, "inputSchema", None)
                if schema is not None:
                    return serialize_input_schema(schema)
                args_schema = getattr(tool, "args_schema", None)
                return serialize_input_schema(args_schema)

            client = MultiServerMCPClient(
                connections={
                    "tools-service": self._mcp_connection(tools_service_url),
                }
            )
            tools = await client.get_tools()
            return {
                "tools": [
                    {
                        "name": tool.name,
                        "description": getattr(tool, "description", "") or "",
                        "input_schema": get_tool_schema(tool),
                    }
                    for tool in tools
                ]
            }
        except Exception as e:
            from core.logger import get_logger

            logger = get_logger(__name__)
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
                    "mcp-tools": self._mcp_connection(url),
                }
            )
            tools = await client.get_tools()

            tool = next((t for t in tools if t.name == tool_name), None)
            if not tool:
                return {
                    "error": t("mcp.tool_not_found", tool_name=tool_name),
                    "result": None,
                }

            result = await tool.ainvoke(arguments)

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

    def _mcp_connection(self, url: str) -> dict[str, Any]:
        """Build an authenticated streamable HTTP MCP client connection.

        This path (unlike the LangGraph agent's own MCP client construction
        in agents/configurable_mcp_agent.py and agents/perceptrons/mcp_perceptron.py)
        is used by human-facing endpoints -- e.g. the tools playground -- where a
        person reads the tool's raw output directly, with no LLM in between to
        paraphrase it into the user's language. So the caller's locale (already
        resolved by this service's own I18nMiddleware from the incoming request)
        is forwarded to tools-service via X-Language.
        """
        connection: dict[str, Any] = {
            "transport": "streamable_http",
            "url": self._ensure_mcp_url_path(url),
        }
        headers: dict[str, str] = {"X-Language": get_locale()}
        token = (env.INTERNAL_SERVICE_TOKEN or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection["headers"] = headers
        return connection


# Singleton instance
_proxy_controller: ProxyController | None = None


def get_proxy_controller() -> ProxyController:
    """Get the singleton ProxyController instance."""
    global _proxy_controller
    if _proxy_controller is None:
        _proxy_controller = ProxyController()
    return _proxy_controller
