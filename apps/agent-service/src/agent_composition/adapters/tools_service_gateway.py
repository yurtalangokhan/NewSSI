"""HTTP-based tool gateway that calls tools-service with trusted context.

Additive adapter. Does not replace the existing MultiServerMCPClient path.
Use this gateway when tools must be called with authenticated user/tenant
identity carried in transport headers (the trusted invocation contract).
"""

from __future__ import annotations

import httpx

from ..domain.errors import ToolInvocationError
from ..domain.ports import (
    ToolBinding,
    ToolDescriptor,
    ToolGateway,
    ToolInvocation,
    ToolResult,
)
from ..domain.trusted_context import INTERNAL_AUTH_HEADER, build_transport_headers


class ToolsServiceToolBinding(ToolBinding):
    """ToolBinding that calls one tool on tools-service via HTTP POST."""

    def __init__(
        self,
        descriptor: ToolDescriptor,
        service_url: str,
        internal_token: str,
    ) -> None:
        self.descriptor = descriptor
        self._service_url = service_url.rstrip("/")
        self._internal_token = internal_token

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        headers = build_transport_headers(invocation.trusted_context, self._internal_token)
        headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._service_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": self.descriptor.key,
                            "arguments": dict(invocation.model_arguments),
                        },
                        "id": 1,
                    },
                    headers=headers,
                )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise ToolInvocationError(
                    message=data["error"].get("message", "Tool call failed"),
                    details={"code": data["error"].get("code")},
                )
            result = data.get("result", {})
            return ToolResult(
                output=result.get("content", [{"type": "text", "text": ""}]),
                metadata={"tool": self.descriptor.key},
            )
        except httpx.HTTPStatusError as exc:
            raise ToolInvocationError(
                message=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                details={"status": exc.response.status_code},
            )
        except Exception as exc:
            raise ToolInvocationError(
                message=str(exc),
                details={"type": type(exc).__name__},
            )


class ToolsServiceToolGateway(ToolGateway):
    """ToolGateway that lists and invokes tools via tools-service HTTP transport.

    Trusted context is read from the invocation's ``trusted_context`` field and
    sent only in transport headers (never in model_visible arguments).
    """

    def __init__(
        self,
        service_url: str,
        internal_token: str,
        *,
        tools_cache_ttl: float = 300.0,
    ) -> None:
        self._service_url = service_url.rstrip("/")
        self._internal_token = internal_token
        self._tools_cache_ttl = tools_cache_ttl
        self._loaded = False
        self._cached_tools: list[ToolDescriptor] | None = None
        self._cache_expires_at: float = 0.0

    async def load(self) -> None:
        self._loaded = True

    async def describe(self) -> tuple[ToolDescriptor, ...]:
        if self._cached_tools is not None:
            return tuple(self._cached_tools)
        headers = {INTERNAL_AUTH_HEADER: self._internal_token}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._service_url}/mcp",
                    headers=headers,
                )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("tools", [])
            self._cached_tools = [
                ToolDescriptor(
                    key=t["name"],
                    description=t.get("description", ""),
                    required_trusted_bindings=(),
                )
                for t in tools
            ]
        except Exception:
            self._cached_tools = []
        return tuple(self._cached_tools)

    async def resolve(self, keys: tuple[str, ...]) -> tuple[ToolBinding, ...]:
        all_tools = await self.describe()
        resolved = []
        for key in keys:
            for tool in all_tools:
                if tool.key == key:
                    resolved.append(
                        ToolsServiceToolBinding(
                            descriptor=tool,
                            service_url=self._service_url,
                            internal_token=self._internal_token,
                        )
                    )
                    break
        return tuple(resolved)

    async def close(self) -> None:
        self._loaded = False
        self._cached_tools = None
