"""MCP Tool Service - manages tool definitions and syncing from providers."""

from __future__ import annotations

import re
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from core.db.repositories import MCPProviderRepository, MCPToolRepository
from core.logger import get_logger
from service.MCPCredentialService import MCPCredentialService

logger = get_logger(__name__)


def _server_slug(name: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return slug or "mcp"


def qualify_mcp_tool_name(provider_row: dict[str, Any], raw_name: str) -> str:
    """Server-scoped tool identity, e.g. ``deepwiki__ask_question``.

    Two external MCP servers may expose a tool with the same raw name; agent
    tool selection and the runtime tool pool key on this qualified name so they
    stay distinct. The raw name is still used to actually call the server.
    """
    return f"{_server_slug(provider_row.get('name'))}__{raw_name}"


class MCPToolService:
    """Service for managing MCP tools."""

    _instance: MCPToolService | None = None
    _tool_repo: MCPToolRepository | None = None
    _provider_repo: MCPProviderRepository | None = None

    def __init__(
        self,
        tool_repo: MCPToolRepository | None = None,
        provider_repo: MCPProviderRepository | None = None,
    ):
        self._tool_repo = tool_repo or MCPToolRepository()
        self._provider_repo = provider_repo or MCPProviderRepository()

    @classmethod
    def get_instance(cls) -> MCPToolService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_tools(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await self._tool_repo.list_all(include_inactive)

    async def list_tools_by_provider(
        self,
        provider_id: str,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        return await self._tool_repo.list_by_provider(provider_id, include_inactive)

    async def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        return await self._tool_repo.get_by_id(tool_id)

    async def get_tool_by_name(
        self,
        name: str,
        provider_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._tool_repo.get_by_name(name, provider_id)

    async def list_categories(self) -> list[str]:
        return await self._tool_repo.list_categories()

    async def get_tools_by_category(self, category: str) -> list[dict[str, Any]]:
        return await self._tool_repo.get_by_category(category)

    async def sync_tools_from_provider(
        self, provider_ref: str | int, *, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Discover tools from a provider (with auth) and upsert them.

        ``provider_ref`` may be the surrogate ``int_id`` (from the admin API) or
        the UUID string (legacy ``/mcp-providers`` callers). Returns the
        provider's tools in frontend ``ToolSnapshot`` shape.
        """
        if isinstance(provider_ref, int):
            provider = await self._provider_repo.get_by_int_id(provider_ref)
        else:
            provider = await self._provider_repo.get_by_id(str(provider_ref))
        if not provider:
            raise ValueError(f"Provider {provider_ref} not found")
        if not provider.get("url"):
            raise ValueError(f"Provider {provider_ref} has no URL")

        headers = await MCPCredentialService.get_instance().resolve_headers(
            provider, user_id=user_id
        )
        raw_tools = await self._fetch_tools_via_client(
            provider["url"], provider.get("transport", "streamable_http"), headers
        )
        normalized = self._normalize_tools(raw_tools)
        await self._tool_repo.bulk_upsert(provider["id"], normalized)

        rows = await self._tool_repo.list_by_provider(provider["id"], include_inactive=False)
        return [self.to_tool_snapshot(r, provider) for r in rows]

    async def _fetch_tools_via_client(
        self, mcp_url: str, transport: str, headers: dict[str, str]
    ) -> list[dict[str, Any]]:
        conn: dict[str, Any] = {
            "transport": "sse" if str(transport).lower() == "sse" else "streamable_http",
            "url": mcp_url,
        }
        if headers:
            conn["headers"] = headers
        try:
            client = MultiServerMCPClient({"sync": conn})
            tools = await client.get_tools()
        except Exception as exc:  # noqa: BLE001 - normalized for the route layer
            raise RuntimeError(f"failed to reach MCP server: {exc}") from exc

        result: list[dict[str, Any]] = []
        for tool in tools:
            schema = getattr(tool, "args_schema", None) or getattr(tool, "tool_call_schema", None)
            if hasattr(schema, "model_json_schema"):
                schema = schema.model_json_schema()
            result.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "inputSchema": schema if isinstance(schema, dict) else {},
                }
            )
        return result

    def to_tool_snapshot(
        self, tool_row: dict[str, Any], provider_row: dict[str, Any]
    ) -> dict[str, Any]:
        """Map a ``mcp_tool`` row to the frontend ``ToolSnapshot`` shape."""
        enabled = bool(tool_row.get("enabled", True))
        return {
            "id": tool_row["int_id"],
            "name": tool_row["name"],
            "qualified_name": qualify_mcp_tool_name(provider_row, tool_row["name"]),
            "display_name": tool_row["name"],
            "description": tool_row.get("description") or "",
            "definition": None,
            "custom_headers": [],
            "in_code_tool_id": None,
            "passthrough_auth": provider_row.get("auth_type") == "PT_OAUTH",
            "oauth_config_id": None,
            "oauth_config_name": None,
            "mcp_server_id": provider_row.get("int_id"),
            "user_id": None,
            "enabled": enabled,
            "chat_selectable": True,
            "agent_creation_selectable": True,
            "default_enabled": enabled,
            "input_schema": tool_row.get("input_schema") or {},
        }

    async def execute_tool(
        self,
        int_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Invoke one tool on an external MCP server.

        Returns ``{"result": <value>, "error": <str|None>}``. Only a missing
        provider raises (``ValueError``); tool-level failures are returned in
        ``error`` so the playground can show them.
        """
        provider = await self._provider_repo.get_by_int_id(int_id)
        if not provider or not provider.get("url"):
            raise ValueError(f"Provider {int_id} not found")

        try:
            headers = await MCPCredentialService.get_instance().resolve_headers(
                provider, user_id=user_id
            )
            transport = (
                "sse" if str(provider.get("transport", "")).lower() == "sse" else "streamable_http"
            )
            conn: dict[str, Any] = {"transport": transport, "url": provider["url"]}
            if headers:
                conn["headers"] = headers
            client = MultiServerMCPClient({"exec": conn})
            tools = await client.get_tools()
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool is None:
                return {
                    "result": None,
                    "error": f"tool {tool_name!r} not found on server",
                }
            result = await tool.ainvoke(arguments)
            return {"result": result, "error": None}
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as data
            logger.warning("MCP execute_tool %s/%s failed: %s", int_id, tool_name, exc)
            return {"result": None, "error": str(exc)}

    async def set_tools_enabled(self, int_ids: list[int], enabled: bool) -> int:
        return await self._tool_repo.set_enabled(int_ids, enabled)

    async def list_snapshots_for_provider(self, int_id: int) -> list[dict[str, Any]]:
        provider = await self._provider_repo.get_by_int_id(int_id)
        if not provider:
            raise ValueError(f"Provider {int_id} not found")
        rows = await self._tool_repo.list_by_provider(provider["id"], include_inactive=False)
        return [self.to_tool_snapshot(r, provider) for r in rows]

    def _normalize_tools(self, mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for tool in mcp_tools:
            input_schema = tool.get("inputSchema") or tool.get("input_schema", {})
            category = None
            tags = []
            description = tool.get("description", "")

            if "[category:" in description:
                try:
                    cat_start = description.find("[category:") + len("[category:")
                    cat_end = description.find("]", cat_start)
                    if cat_end > cat_start:
                        category = description[cat_start:cat_end]
                except Exception:
                    pass

            if "[category_label:" in description:
                try:
                    label_start = description.find("[category_label:") + len("[category_label:")
                    label_end = description.find("]", label_start)
                    if label_end > label_start:
                        label = description[label_start:label_end]
                        tags.append(label)
                except Exception:
                    pass

            normalized.append(
                {
                    "name": tool.get("name", ""),
                    "description": description.split("[category:")[0]
                    .split("[category_label:")[0]
                    .strip(),
                    "input_schema": input_schema,
                    "metadata": {
                        "original": tool,
                    },
                    "category": category,
                    "tags": tags,
                }
            )
        return normalized

    async def sync_all_providers(self) -> dict[str, int]:
        providers = await self._provider_repo.list_all(include_inactive=False)
        results = {}
        for provider in providers:
            if provider.get("is_active") and provider.get("url"):
                try:
                    snapshots = await self.sync_tools_from_provider(provider["id"])
                    results[provider["name"]] = len(snapshots)
                except Exception as e:
                    logger.warning(f"Failed to sync provider {provider['name']}: {e}")
                    results[provider["name"]] = 0
        return results

    async def create_tool(
        self,
        provider_id: str,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        return await self._tool_repo.create(
            provider_id=provider_id,
            name=name,
            description=description,
            input_schema=input_schema,
            category=category,
        )

    async def set_tool_active(self, tool_id: str, is_active: bool) -> bool:
        return await self._tool_repo.set_active(tool_id, is_active)

    async def delete_tool(self, tool_id: str) -> bool:
        return await self._tool_repo.delete(tool_id)

    async def delete_tools_by_provider(self, provider_id: str) -> int:
        return await self._tool_repo.delete_by_provider(provider_id)
