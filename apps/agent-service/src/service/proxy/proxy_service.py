"""Proxy service - handles external service proxy logic (MCP, Ollama, RAG)."""

import json
from typing import Any

from config_manager import env
from error_contract import (
    ApplicationError,
    DependencyResponseError,
    DependencyUnavailableError,
    NotFoundError,
    UnauthorizedError,
    from_httpx_error,
    raise_for_httpx_response,
)
import httpx
from localization import get_locale

from core.http import outbound
from core.observability.logger import get_logger
from integrations.rag_client import list_collection_records
from service.common.base import BaseService

logger = get_logger(__name__)


class ProxyService(BaseService):
    """Service for proxy endpoints to external services.

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
                        "input_schema": (getattr(tool, "args_schema", None) and tool.args_schema.model_json_schema())
                        or {},
                    }
                    for tool in tools
                ]
            }
        except ApplicationError:
            raise
        except Exception as exc:
            # Final external MCP boundary: preserve the response shape without SDK text.
            logger.exception("External MCP tool discovery failed")
            raise DependencyUnavailableError(
                code="proxy.mcp_unavailable", message_key="errors.proxy.mcp_unavailable"
            ) from exc

    async def get_builtin_mcp_tools(self, tools_service_url: str) -> dict[str, Any]:
        """Get list of available MCP tools from the builtin tools-service."""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            def serialize_input_schema(schema: Any) -> dict[str, Any]:
                if not schema:
                    return {}
                if isinstance(schema, dict):
                    return schema

                is_class = isinstance(schema, type)

                if is_class and hasattr(schema, "model_json_schema"):
                    try:
                        return schema.model_json_schema()
                    except (AttributeError, TypeError, ValueError):
                        pass

                if not is_class and hasattr(schema, "model_dump"):
                    try:
                        return schema.model_dump()
                    except (AttributeError, TypeError, ValueError):
                        pass

                if hasattr(schema, "dict"):
                    try:
                        return schema.dict()
                    except (AttributeError, TypeError, ValueError):
                        pass

                if hasattr(schema, "__dict__"):
                    return dict(schema.__dict__)

                try:
                    return json.loads(json.dumps(schema, default=str))
                except (TypeError, ValueError, OverflowError):
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
        except ApplicationError:
            raise
        except Exception as exc:
            # Final tools-service boundary: optional discovery degrades safely.
            logger.exception("Built-in MCP tool discovery failed")
            raise DependencyUnavailableError(
                code="proxy.mcp_unavailable", message_key="errors.proxy.mcp_unavailable"
            ) from exc

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
                raise NotFoundError(code="proxy.tool_not_found", message_key="errors.proxy.tool_not_found")

            result = await tool.ainvoke(arguments)

            return {"result": result, "error": None}
        except ApplicationError:
            raise
        except Exception as exc:
            # Tool execution is an unknown-plugin isolation boundary.
            logger.exception("External MCP tool %s failed", tool_name)
            raise DependencyUnavailableError(
                code="proxy.mcp_unavailable", message_key="errors.proxy.mcp_unavailable"
            ) from exc

    # =========================================================================
    # Ollama
    # =========================================================================

    async def get_ollama_models(self, ollama_url: str, default_model: str) -> dict[str, Any]:
        """Get list of available Ollama models."""

        try:
            response = await outbound.request(
                outbound.OLLAMA,
                "GET",
                f"{ollama_url}/api/tags",
                timeout=10.0,
            )
            raise_for_httpx_response(response)
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models, "default": default_model}
        except httpx.HTTPError as exc:
            raise from_httpx_error(exc) from exc
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            logger.exception("Ollama model discovery failed")
            raise DependencyResponseError(
                code="proxy.ollama_unavailable", message_key="errors.proxy.ollama_unavailable"
            ) from exc

    # =========================================================================
    # RAG Collections
    # =========================================================================

    async def get_rag_collections(self, access_token: str | None = None) -> dict[str, Any]:
        """Return caller-visible RAG collections and preserve typed failures."""
        if not access_token:
            raise UnauthorizedError()
        return {"collections": await list_collection_records(access_token=access_token)}

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


_proxy_service: ProxyService | None = None


def get_proxy_service() -> ProxyService:
    global _proxy_service
    if _proxy_service is None:
        _proxy_service = ProxyService()
    return _proxy_service
