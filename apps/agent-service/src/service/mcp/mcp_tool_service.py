"""MCP Tool Service - manages tool definitions and syncing from providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Any

from error_contract import (
    ApplicationError,
    ConfigurationError,
    DependencyUnavailableError,
    NotFoundError,
    from_httpx_error,
)
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient
from localization import t

from core.observability.logger import get_logger
from core.security.mcp.mcp_ssrf_guard import validate_mcp_server_url
from infrastructure.db.persistence_gateway import mcp_provider_repository, mcp_tool_repository
from schemas.mcp_admin import (
    MCPProviderEntity,
    MCPToolEntity,
    ToolSnapshotResponse,
)
from service.mcp.mcp_credential_service import MCPCredentialService

if TYPE_CHECKING:
    # Type only: the repository itself comes from the gateway at
    # runtime, so the class is never reachable here.
    from infrastructure.db.repositories import (
        MCPProviderRepository,
        MCPToolRepository,
    )


logger = get_logger(__name__)

# A non-MCP endpoint (a plain website) answers 200 with HTML, which stalls the
# MCP adapter until this bound; the probe treats the timeout as "not a usable
# MCP server". Kept short so an admin's Verify click returns promptly.
_PROBE_TIMEOUT_SECONDS = 10.0


def _server_slug(name: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return slug or "mcp"


def qualify_mcp_tool_name(provider_row: dict[str, Any] | MCPProviderEntity, raw_name: str) -> str:
    """Server-scoped tool identity, e.g. ``deepwiki__ask_question``.

    Two external MCP servers may expose a tool with the same raw name; agent
    tool selection and the runtime tool pool key on this qualified name so they
    stay distinct. The raw name is still used to actually call the server.
    """
    return f"{_server_slug(provider_row.get('name'))}__{raw_name}"


@dataclass
class MCPProbeResult:
    """Outcome of a live MCP handshake against an admin-supplied URL.

    ``ok`` -> the endpoint answered ``initialize``/``tools/list``.
    ``auth_required`` -> it answered with a 401/403 challenge, i.e. a valid MCP
    resource the enterprise admin still has to authenticate.
    Otherwise the endpoint is not a usable MCP server (reason ``not_mcp``).
    """

    ok: bool
    auth_required: bool
    tools: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None


def _iter_errors(error: BaseException) -> list[BaseException]:
    """Flatten an exception tree (``ExceptionGroup`` members and chained causes).

    The MCP adapter reports through anyio task groups, so a 401 arrives as an
    ``ExceptionGroup`` wrapping the ``httpx.HTTPStatusError`` rather than the
    error itself.
    """
    flat: list[BaseException] = []
    seen: set[int] = set()
    stack: list[BaseException] = [error]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        flat.append(current)
        if isinstance(current, BaseExceptionGroup):
            stack.extend(current.exceptions)
        if current.__cause__ is not None:
            stack.append(current.__cause__)
    return flat


def _convert_tools(tools: list[Any]) -> list[dict[str, Any]]:
    """Map adapter tool objects to the ``{name, description, inputSchema}`` shape
    ``_normalize_tools`` (and therefore ``bulk_upsert``) expects."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        schema = getattr(tool, "args_schema", None) or getattr(tool, "tool_call_schema", None)
        if hasattr(schema, "model_json_schema"):
            schema = schema.model_json_schema()
        converted.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "inputSchema": schema if isinstance(schema, dict) else {},
            }
        )
    return converted


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
        self._tool_repo = tool_repo or mcp_tool_repository()
        self._provider_repo = provider_repo or mcp_provider_repository()

    @classmethod
    def get_instance(cls) -> MCPToolService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_tools(self, include_inactive: bool = False) -> list[MCPToolEntity]:
        rows = await self._tool_repo.list_all(include_inactive)
        return [MCPToolEntity.model_validate(r) if not isinstance(r, MCPToolEntity) else r for r in rows]

    async def list_tools_by_provider(
        self,
        provider_id: str,
        include_inactive: bool = False,
    ) -> list[MCPToolEntity]:
        rows = await self._tool_repo.list_by_provider(provider_id, include_inactive)
        return [MCPToolEntity.model_validate(r) if not isinstance(r, MCPToolEntity) else r for r in rows]

    async def get_tool(self, tool_id: str) -> MCPToolEntity | None:
        row = await self._tool_repo.get_by_id(tool_id)
        return MCPToolEntity.model_validate(row) if row else None

    async def get_tool_by_name(
        self,
        name: str,
        provider_id: str | None = None,
    ) -> MCPToolEntity | None:
        row = await self._tool_repo.get_by_name(name, provider_id)
        return MCPToolEntity.model_validate(row) if row else None

    async def list_categories(self) -> list[str]:
        return await self._tool_repo.list_categories()

    async def get_tools_by_category(self, category: str) -> list[MCPToolEntity]:
        rows = await self._tool_repo.get_by_category(category)
        return [MCPToolEntity.model_validate(r) if not isinstance(r, MCPToolEntity) else r for r in rows]

    async def _load_provider(self, provider_ref: str | int | dict[str, Any]) -> dict[str, Any]:
        """Resolve a provider from a row, the ``int_id``, or the UUID."""
        if isinstance(provider_ref, dict):
            provider: dict[str, Any] | None = provider_ref
        elif isinstance(provider_ref, int):
            provider = await self._provider_repo.get_by_int_id(provider_ref)
        else:
            provider = await self._provider_repo.get_by_id(str(provider_ref))
        if not provider:
            raise NotFoundError(code="mcp_provider.not_found", message_key="common.not_found")
        if not provider.get("url"):
            raise ConfigurationError()
        return provider

    @staticmethod
    def _connection_config(mcp_url: str, transport: str, headers: dict[str, str]) -> dict[str, Any]:
        conn: dict[str, Any] = {
            "transport": "sse" if str(transport).lower() == "sse" else "streamable_http",
            "url": mcp_url,
        }
        if headers:
            conn["headers"] = headers
        return conn

    async def sync_tools_from_provider(
        self, provider_ref: str | int, *, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Discover tools from a provider (with auth) and upsert them.

        ``provider_ref`` may be the surrogate ``int_id`` (from the admin API) or
        the UUID string (legacy ``/mcp-providers`` callers). Returns the
        provider's tools in frontend ``ToolSnapshot`` shape.
        """
        provider = await self._load_provider(provider_ref)

        headers = await MCPCredentialService.get_instance().resolve_headers(provider, user_id=user_id)
        raw_tools = await self._fetch_tools_via_client(
            provider["url"], provider.get("transport", "streamable_http"), headers
        )
        return await self.upsert_discovered_tools(provider, raw_tools)

    async def upsert_discovered_tools(
        self, provider_ref: str | int | dict[str, Any], raw_tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Persist already-discovered tools and return ``ToolSnapshot`` rows.

        Lets the create/verify flow reuse the tools a probe already fetched
        instead of opening a second MCP session.
        """
        provider = await self._load_provider(provider_ref)
        normalized = self._normalize_tools(raw_tools)
        await self._tool_repo.bulk_upsert(provider["id"], normalized)

        rows = await self._tool_repo.list_by_provider(provider["id"], include_inactive=False)
        return [self.to_tool_snapshot(r, provider) for r in rows]

    async def probe_endpoint(
        self,
        mcp_url: str,
        transport: str = "streamable_http",
        headers: dict[str, str] | None = None,
        *,
        probe_timeout: float = _PROBE_TIMEOUT_SECONDS,
    ) -> MCPProbeResult:
        """Open a real MCP session and classify the result, without persisting.

        Unlike the sync path (which raises), this reports *why* an endpoint is
        unusable so the admin API can reject a non-MCP URL. The URL itself is
        still put through :func:`validate_mcp_server_url`, which raises
        :class:`MCPUrlRejected` for an unsafe address.
        """
        await validate_mcp_server_url(mcp_url)
        conn = self._connection_config(mcp_url, transport, headers or {})
        try:
            tools = await asyncio.wait_for(MultiServerMCPClient({"probe": conn}).get_tools(), probe_timeout)
        except TimeoutError:
            # A plain website answers 200 text/html, which the adapter never
            # finishes reading, so a stalled session is a non-MCP signal.
            logger.info("MCP probe timed out", extra={"mcp_url_host": httpx.URL(mcp_url).host})
            return MCPProbeResult(ok=False, auth_required=False, reason="not_mcp")
        except Exception as exc:  # classified below, never surfaced raw
            result = self._classify_probe_error(exc)
            logger.info(
                "MCP probe rejected the endpoint",
                extra={
                    "mcp_url_host": httpx.URL(mcp_url).host,
                    "auth_required": result.auth_required,
                    "error_types": sorted({type(inner).__name__ for inner in _iter_errors(exc)}),
                },
            )
            return result
        return MCPProbeResult(ok=True, auth_required=False, tools=_convert_tools(tools))

    @staticmethod
    def _classify_probe_error(error: BaseException) -> MCPProbeResult:
        for inner in _iter_errors(error):
            if isinstance(inner, httpx.HTTPStatusError):
                status = inner.response.status_code if inner.response is not None else None
                if status in (401, 403):
                    return MCPProbeResult(ok=False, auth_required=True)
                return MCPProbeResult(ok=False, auth_required=False, reason="not_mcp")
        return MCPProbeResult(ok=False, auth_required=False, reason="not_mcp")

    async def _fetch_tools_via_client(
        self, mcp_url: str, transport: str, headers: dict[str, str]
    ) -> list[dict[str, Any]]:
        # Re-validated here, not only at registration: a hostname that
        # resolved to a public address when the provider was saved can
        # resolve to link-local or private space by the time it is dialled,
        # and this call carries the provider's stored credentials.
        await validate_mcp_server_url(mcp_url)
        conn = self._connection_config(mcp_url, transport, headers)
        try:
            client = MultiServerMCPClient({"sync": conn})
            tools = await client.get_tools()
        except ApplicationError:
            raise
        except httpx.HTTPError as exc:
            raise from_httpx_error(exc) from exc
        except Exception as exc:
            logger.exception("MCP discovery failed")
            raise DependencyUnavailableError() from exc

        return _convert_tools(tools)

    def to_tool_snapshot(
        self,
        tool_row: dict[str, Any] | MCPToolEntity,
        provider_row: dict[str, Any] | MCPProviderEntity,
    ) -> ToolSnapshotResponse:
        """Map a ``mcp_tool`` row to the frontend ``ToolSnapshot`` shape."""
        enabled = bool(tool_row.get("enabled", True))
        return ToolSnapshotResponse(
            id=tool_row["int_id"],
            name=tool_row["name"],
            qualified_name=qualify_mcp_tool_name(provider_row, tool_row["name"]),
            display_name=tool_row["name"],
            description=tool_row.get("description") or "",
            definition=None,
            custom_headers=[],
            in_code_tool_id=None,
            passthrough_auth=provider_row.get("auth_type") == "PT_OAUTH",
            oauth_config_id=None,
            oauth_config_name=None,
            mcp_server_id=provider_row.get("int_id"),
            user_id=None,
            enabled=enabled,
            chat_selectable=True,
            agent_creation_selectable=True,
            default_enabled=enabled,
            input_schema=tool_row.get("input_schema") or {},
        )

    async def execute_tool(
        self,
        int_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Invoke one tool on an external MCP server.

        Returns ``{"result": <value>, "error": <str|None>}``. Typed platform,
        authentication and dependency failures propagate to the public response
        boundary; unknown tool-level failures remain in ``error``.
        """
        provider = await self._provider_repo.get_by_int_id(int_id)
        if not provider:
            raise NotFoundError(code="mcp_provider.not_found", message_key="common.not_found")
        if not provider.get("url"):
            raise ConfigurationError()

        try:
            # Same connect-time re-validation as the refresh path above.
            await validate_mcp_server_url(provider["url"])
            headers = await MCPCredentialService.get_instance().resolve_headers(provider, user_id=user_id)
            transport = "sse" if str(provider.get("transport", "")).lower() == "sse" else "streamable_http"
            conn: dict[str, Any] = {"transport": transport, "url": provider["url"]}
            if headers:
                conn["headers"] = headers
            client = MultiServerMCPClient({"exec": conn})
            tools = await client.get_tools()
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool is None:
                raise NotFoundError(code="proxy.tool_not_found", message_key="errors.proxy.tool_not_found")
            result = await tool.ainvoke(arguments)
            return {"result": result, "error": None}
        except ApplicationError:
            raise
        except httpx.HTTPError as exc:
            raise from_httpx_error(exc) from exc
        except Exception as exc:  # Unknown external tool boundary.
            logger.warning("MCP execute_tool %s/%s failed: %s", int_id, tool_name, exc)
            return {"result": None, "error": t("common.internal_error")}

    async def set_tools_enabled(self, int_ids: list[int], enabled: bool) -> int:
        return await self._tool_repo.set_enabled(int_ids, enabled)

    async def list_snapshots_for_provider(self, int_id: int) -> list[ToolSnapshotResponse]:
        provider = await self._provider_repo.get_by_int_id(int_id)
        if not provider:
            raise NotFoundError(code="mcp_provider.not_found", message_key="common.not_found")
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
                    logger.debug("Failed to parse category for MCP tool %s", tool.get("name"), exc_info=True)

            if "[category_label:" in description:
                try:
                    label_start = description.find("[category_label:") + len("[category_label:")
                    label_end = description.find("]", label_start)
                    if label_end > label_start:
                        label = description[label_start:label_end]
                        tags.append(label)
                except Exception:
                    logger.debug(
                        "Failed to parse category label for MCP tool %s",
                        tool.get("name"),
                        exc_info=True,
                    )

            normalized.append(
                {
                    "name": tool.get("name", ""),
                    "description": description.split("[category:")[0].split("[category_label:")[0].strip(),
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
