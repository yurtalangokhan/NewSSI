"""MCP tool gateway for tools-service with trusted transport headers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from ..domain.errors import ToolInvocationError
from ..domain.ports import ToolBinding, ToolDescriptor, ToolGateway, ToolInvocation, ToolResult
from ..domain.trusted_context import INTERNAL_AUTH_HEADER, build_transport_headers


def _mcp_endpoint(service_url: str) -> str:
    base_url = service_url.rstrip("/")
    return base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"


@asynccontextmanager
async def _open_mcp_session(
    url: str, headers: dict[str, str]
) -> AsyncIterator[ClientSession]:
    """Open and initialize one Streamable HTTP MCP session."""
    async with streamablehttp_client(url, headers=headers) as (read, write, _session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _content_to_dict(content: Any) -> dict[str, Any]:
    if hasattr(content, "model_dump"):
        return content.model_dump(by_alias=True, exclude_none=True)
    result = dict(vars(content))
    for name in ("type", "text", "data", "mimeType", "uri"):
        if hasattr(content, name):
            result[name] = getattr(content, name)
    return result


class ToolsServiceToolBinding(ToolBinding):
    """Binding that invokes one tools-service MCP tool."""

    def __init__(self, descriptor: ToolDescriptor, service_url: str, internal_token: str) -> None:
        self.descriptor = descriptor
        self._mcp_url = _mcp_endpoint(service_url)
        self._internal_token = internal_token

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        headers = build_transport_headers(invocation.trusted_context, self._internal_token)
        headers["Authorization"] = f"Bearer {self._internal_token}"
        try:
            async with _open_mcp_session(self._mcp_url, headers) as session:
                result = await session.call_tool(
                    self.descriptor.key, dict(invocation.model_arguments)
                )
            content = tuple(_content_to_dict(item) for item in result.content)
            if result.isError:
                raise ToolInvocationError(message="Tool call failed")
            return ToolResult(output=content, metadata={"tool": self.descriptor.key})
        except ToolInvocationError:
            raise
        except Exception as exc:
            raise ToolInvocationError(
                message="Tools service is unavailable",
                details={"type": type(exc).__name__},
            ) from exc


class ToolsServiceToolGateway(ToolGateway):
    """Discover and bind tools through tools-service's MCP endpoint."""

    def __init__(
        self,
        service_url: str,
        internal_token: str,
        *,
        tools_cache_ttl: float = 300.0,
    ) -> None:
        self._service_url = service_url.rstrip("/")
        self._mcp_url = _mcp_endpoint(service_url)
        self._internal_token = internal_token
        self._tools_cache_ttl = tools_cache_ttl
        self._loaded = False
        self._cached_tools: list[ToolDescriptor] | None = None
        self._cache_expires_at = 0.0

    async def load(self) -> None:
        self._loaded = True

    async def describe(self) -> tuple[ToolDescriptor, ...]:
        if self._cached_tools is not None and monotonic() < self._cache_expires_at:
            return tuple(self._cached_tools)

        headers = {
            "Authorization": f"Bearer {self._internal_token}",
            INTERNAL_AUTH_HEADER: self._internal_token,
        }
        tools: list[Any] = []
        cursor: str | None = None
        try:
            async with _open_mcp_session(self._mcp_url, headers) as session:
                while True:
                    result = await session.list_tools(cursor=cursor)
                    tools.extend(result.tools)
                    cursor = result.nextCursor
                    if cursor is None:
                        break
        except Exception as exc:
            raise ToolInvocationError(
                message="Unable to discover tools-service MCP tools",
                details={"type": type(exc).__name__},
            ) from exc

        self._cached_tools = [
            ToolDescriptor(
                key=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in tools
        ]
        self._cache_expires_at = monotonic() + self._tools_cache_ttl
        return tuple(self._cached_tools)

    async def resolve(self, keys: tuple[str, ...]) -> tuple[ToolBinding, ...]:
        descriptors = {tool.key: tool for tool in await self.describe()}
        return tuple(
            ToolsServiceToolBinding(descriptors[key], self._service_url, self._internal_token)
            for key in keys
            if key in descriptors
        )

    async def close(self) -> None:
        self._loaded = False
        self._cached_tools = None
        self._cache_expires_at = 0.0
