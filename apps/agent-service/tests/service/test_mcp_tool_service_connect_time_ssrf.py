"""A registered MCP provider is re-validated every time it is dialled.

`MCPProviderService` checks a server URL when it is registered or updated,
but `MCPToolService` -- the sync path that refreshes a provider's tool list
and the playground path that executes a tool on it -- read the stored URL
and connected straight to it. A name that resolved to a public address at
registration and to 169.254.169.254 afterwards (DNS rebinding, or simply a
record the owner changed later) therefore reached the metadata service with
the platform's own credentials attached. The agent loader already
re-validates at connect time; these two did not.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.security.mcp.mcp_ssrf_guard import MCPUrlRejected
from service.mcp.mcp_tool_service import MCPToolService

PROVIDER = {
    "id": "prov-1",
    "int_id": 7,
    "url": "http://internal.example.com/mcp",
    "transport": "streamable_http",
    "auth_type": "NONE",
}


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> MCPToolService:
    svc = MCPToolService.__new__(MCPToolService)
    svc._provider_repo = SimpleNamespace(
        get_by_int_id=AsyncMock(return_value=dict(PROVIDER)),
        get_by_id=AsyncMock(return_value=dict(PROVIDER)),
    )
    svc._tool_repo = SimpleNamespace(
        bulk_upsert=AsyncMock(),
        list_by_provider=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "service.mcp.mcp_credential_service.MCPCredentialService.get_instance",
        lambda: SimpleNamespace(resolve_headers=AsyncMock(return_value={})),
    )
    return svc


@pytest.fixture
def rejecting(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    async def _reject(url: str) -> str:
        seen.append(url)
        raise MCPUrlRejected("blocked")

    monkeypatch.setattr("service.mcp.mcp_tool_service.validate_mcp_server_url", _reject)
    monkeypatch.setattr(
        "service.mcp.mcp_tool_service.MultiServerMCPClient",
        lambda *a, **kw: pytest.fail("connected to a rejected URL"),
    )
    return seen


@pytest.mark.asyncio
async def test_the_tool_refresh_revalidates_before_connecting(service, rejecting):
    with pytest.raises(MCPUrlRejected):
        await service._fetch_tools_via_client(PROVIDER["url"], "streamable_http", {})

    assert rejecting == [PROVIDER["url"]]


@pytest.mark.asyncio
async def test_executing_a_tool_revalidates_before_connecting(service, rejecting):
    # A rejected URL is a platform policy decision: it reaches the caller as the
    # typed 422, not as a tool-level error string.
    with pytest.raises(MCPUrlRejected):
        await service.execute_tool(7, "whoami", {}, user_id="u1")

    assert rejecting == [PROVIDER["url"]]


@pytest.mark.asyncio
async def test_an_accepted_url_still_connects(service, monkeypatch):
    monkeypatch.setattr(
        "service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)
    )
    connected: list[dict] = []

    class _Client:
        def __init__(self, connections: dict) -> None:
            connected.append(connections)

        async def get_tools(self) -> list:
            return []

    monkeypatch.setattr("service.mcp.mcp_tool_service.MultiServerMCPClient", _Client)

    assert await service._fetch_tools_via_client(PROVIDER["url"], "sse", {}) == []
    assert connected and connected[0]["sync"]["url"] == PROVIDER["url"]
