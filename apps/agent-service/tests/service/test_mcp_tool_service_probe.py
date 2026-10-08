"""`MCPToolService.probe_endpoint` classifies an admin URL by a live handshake.

A registration URL used to be accepted on syntax alone, so a plain website
(`https://www.deneme.com`) registered as an "MCP server". The probe opens a real
session and reports whether the endpoint is an MCP server (`ok`), an MCP
resource that needs authentication (`auth_required`), or neither (`not_mcp`).

The failure shapes are the ones the adapter actually raises (verified against
local servers): a 401/403 arrives as an ``ExceptionGroup`` wrapping
``httpx.HTTPStatusError``; a non-MCP HTML endpoint stalls until the timeout; a
bad path surfaces ``McpError('Session terminated')``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.security.mcp.mcp_ssrf_guard import MCPUrlRejected


def _service():
    from service.mcp.mcp_tool_service import MCPToolService

    return MCPToolService(tool_repo=AsyncMock(), provider_repo=AsyncMock())


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://remote.example.com/mcp")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


def _fake_tool(name: str = "list_prs"):
    tool = MagicMock()
    tool.name = name
    tool.description = "List PRs"
    tool.args_schema = {"type": "object"}
    return tool


@pytest.mark.asyncio
async def test_ok_endpoint_returns_discovered_tools():
    svc = _service()
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[_fake_tool()])

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value="https://remote.example.com/mcp")),
    ):
        result = await svc.probe_endpoint("https://remote.example.com/mcp")

    assert result.ok is True
    assert result.auth_required is False
    assert result.reason is None
    assert result.tools == [
        {"name": "list_prs", "description": "List PRs", "inputSchema": {"type": "object"}}
    ]


@pytest.mark.asyncio
async def test_401_challenge_is_reported_as_auth_required():
    svc = _service()
    client = MagicMock()
    client.get_tools = AsyncMock(
        side_effect=ExceptionGroup("task group", [_http_status_error(401)])
    )

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value="https://remote.example.com/mcp")),
    ):
        result = await svc.probe_endpoint("https://remote.example.com/mcp")

    assert result.ok is False
    assert result.auth_required is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_404_path_is_not_a_mcp_server():
    svc = _service()
    client = MagicMock()
    client.get_tools = AsyncMock(
        side_effect=ExceptionGroup("task group", [_http_status_error(404)])
    )

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value="https://remote.example.com/not-mcp")),
    ):
        result = await svc.probe_endpoint("https://remote.example.com/not-mcp")

    assert result.ok is False
    assert result.auth_required is False
    assert result.reason == "not_mcp"


@pytest.mark.asyncio
async def test_connection_failure_is_not_a_mcp_server():
    svc = _service()
    client = MagicMock()
    client.get_tools = AsyncMock(
        side_effect=ExceptionGroup("task group", [httpx.ConnectError("All connection attempts failed")])
    )

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value="https://down.example.com/mcp")),
    ):
        result = await svc.probe_endpoint("https://down.example.com/mcp")

    assert result.ok is False
    assert result.auth_required is False
    assert result.reason == "not_mcp"


@pytest.mark.asyncio
async def test_stalled_website_times_out_and_is_not_a_mcp_server():
    svc = _service()

    class _StallingClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def get_tools(self):
            await asyncio.sleep(5)
            return []

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", _StallingClient),
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value="https://www.deneme.com")),
    ):
        result = await svc.probe_endpoint("https://www.deneme.com", probe_timeout=0.01)

    assert result.ok is False
    assert result.auth_required is False
    assert result.reason == "not_mcp"


@pytest.mark.asyncio
async def test_an_unsafe_url_is_rejected_before_any_connection():
    svc = _service()

    async def _reject(_url: str) -> str:
        raise MCPUrlRejected("blocked")

    with (
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", _reject),
        patch(
            "service.mcp.mcp_tool_service.MultiServerMCPClient",
            lambda *a, **kw: pytest.fail("connected to a rejected URL"),
        ),
    ):
        with pytest.raises(MCPUrlRejected):
            await svc.probe_endpoint("http://169.254.169.254/mcp")


@pytest.mark.asyncio
async def test_upsert_discovered_tools_reuses_a_probed_provider():
    svc = _service()
    svc._provider_repo.get_by_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
        "name": "X",
    }
    svc._tool_repo.list_by_provider = AsyncMock(
        return_value=[{"int_id": 1, "name": "t", "description": "", "enabled": True}]
    )

    out = await svc.upsert_discovered_tools("p1", [{"name": "t", "description": "", "inputSchema": {}}])

    svc._tool_repo.bulk_upsert.assert_awaited_once()
    assert [o["name"] for o in out] == ["t"]
