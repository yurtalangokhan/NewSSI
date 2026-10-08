"""Create/update verify the URL as MCP, and the admin Verify action is backed.

A registered provider used to be persisted no matter what the URL answered, so
a plain website entered the catalog. Now `create_mcp_server` probes before it
persists anything: an MCP handshake or a 401/403 challenge registers the provider
(status stays `CREATED`, so it is only offered in the actions-page picker), and
anything else is rejected with 422 without ever writing a row.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from error_contract import ValidationFailedError
from schemas.mcp_admin import (
    MCPServerCreateBody,
    MCPServerUpdateBody,
    MCPServerValidateBody,
)
from service.mcp.mcp_tool_service import MCPProbeResult

USER = SimpleNamespace(user_id="u1", email="admin@acme.io")
PROVIDER = {
    "id": "p1",
    "int_id": 1000,
    "name": "X",
    "url": "https://x/mcp",
    "transport": "streamable_http",
    "server_status": "CREATED",
}


def _service(probe: MCPProbeResult, *, provider_svc=None, tool_svc=None):
    from service.mcp.mcp_server_admin_application_service import (
        MCPServerAdminApplicationService,
    )

    provider_svc = provider_svc or MagicMock()
    provider_svc.create_provider = AsyncMock(return_value=dict(PROVIDER))
    provider_svc.update_provider = AsyncMock(return_value=dict(PROVIDER))
    provider_svc.set_status = AsyncMock(return_value=True)
    provider_svc.delete_provider = AsyncMock(return_value=True)
    provider_svc.resolve_provider = AsyncMock(return_value=dict(PROVIDER))
    provider_svc.to_mcp_server_dto = AsyncMock(return_value={"id": 1000})

    tool_svc = tool_svc or MagicMock()
    tool_svc.probe_endpoint = AsyncMock(return_value=probe)
    tool_svc.upsert_discovered_tools = AsyncMock(return_value=[])
    tool_svc.delete_tools_by_provider = AsyncMock(return_value=0)

    credential_svc = MagicMock()
    credential_svc.clear_credentials = AsyncMock()

    svc = MCPServerAdminApplicationService(
        provider_service=lambda: provider_svc,
        tool_service=lambda: tool_svc,
        oauth_service=lambda: MagicMock(),
        credential_service=lambda: credential_svc,
    )
    return svc, provider_svc, tool_svc


@pytest.mark.asyncio
async def test_a_live_handshake_registers_without_connecting():
    """Registering on the config page must not look like adding on the actions page."""
    probe = MCPProbeResult(ok=True, auth_required=False, tools=[{"name": "t"}])
    svc, provider_svc, tool_svc = _service(probe)

    await svc.create_mcp_server(
        body=MCPServerCreateBody(name="X", server_url="https://x/mcp"), user=USER
    )

    # Verified, but left in the registered state: no tools, no status change.
    tool_svc.upsert_discovered_tools.assert_not_awaited()
    provider_svc.set_status.assert_not_awaited()
    provider_svc.delete_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_auth_challenge_is_kept_as_registered():
    probe = MCPProbeResult(ok=False, auth_required=True)
    svc, provider_svc, tool_svc = _service(probe)

    await svc.create_mcp_server(
        body=MCPServerCreateBody(name="X", server_url="https://x/mcp"), user=USER
    )

    provider_svc.set_status.assert_not_awaited()
    tool_svc.upsert_discovered_tools.assert_not_awaited()
    provider_svc.delete_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_non_mcp_url_is_rejected_with_422_before_anything_is_persisted():
    probe = MCPProbeResult(ok=False, auth_required=False, reason="not_mcp")
    svc, provider_svc, _tool_svc = _service(probe)

    with pytest.raises(ValidationFailedError) as exc:
        await svc.create_mcp_server(
            body=MCPServerCreateBody(name="X", server_url="https://www.deneme.com"),
            user=USER,
        )

    assert exc.value.status_code == 422
    provider_svc.create_provider.assert_not_awaited()
    provider_svc.delete_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_reports_validity_and_tool_count():
    probe = MCPProbeResult(
        ok=True, auth_required=False, tools=[{"name": "a"}, {"name": "b"}]
    )
    svc, _provider_svc, _tool_svc = _service(probe)

    out = await svc.validate_mcp_server(
        body=MCPServerValidateBody(server_url="https://x/mcp")
    )

    assert out == {"valid": True, "auth_required": False, "tool_count": 2}


@pytest.mark.asyncio
async def test_verify_reports_an_auth_protected_server_as_valid():
    probe = MCPProbeResult(ok=False, auth_required=True)
    svc, _provider_svc, _tool_svc = _service(probe)

    out = await svc.validate_mcp_server(
        body=MCPServerValidateBody(server_url="https://x/mcp")
    )

    assert out == {"valid": True, "auth_required": True, "tool_count": 0}


@pytest.mark.asyncio
async def test_repointing_a_provider_is_verified_before_it_is_persisted():
    probe = MCPProbeResult(ok=True, auth_required=False, tools=[])
    svc, provider_svc, tool_svc = _service(probe)
    provider_svc.update_provider = AsyncMock(
        return_value={**PROVIDER, "url": "https://y/mcp"}
    )

    await svc.update_mcp_server(
        server_id="1000",
        body=MCPServerUpdateBody(server_url="https://y/mcp"),
        user=USER,
    )

    tool_svc.probe_endpoint.assert_awaited_once()
    provider_svc.update_provider.assert_awaited_once()
    provider_svc.set_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_name_only_update_does_not_probe():
    probe = MCPProbeResult(ok=True, auth_required=False, tools=[])
    svc, provider_svc, tool_svc = _service(probe)

    await svc.update_mcp_server(
        server_id="1000", body=MCPServerUpdateBody(name="Renamed"), user=USER
    )

    tool_svc.probe_endpoint.assert_not_awaited()
    provider_svc.update_provider.assert_awaited_once()


@pytest.mark.asyncio
async def test_repointing_a_connected_provider_drops_its_credentials_and_tools():
    """Stored credentials were issued for the old host; never replay them to a new one."""
    probe = MCPProbeResult(ok=True, auth_required=False, tools=[])
    svc, provider_svc, tool_svc = _service(probe)
    provider_svc.resolve_provider = AsyncMock(
        return_value={**PROVIDER, "server_status": "CONNECTED"}
    )

    await svc.update_mcp_server(
        server_id="1000",
        body=MCPServerUpdateBody(server_url="https://y/mcp"),
        user=USER,
    )

    svc.credential_service.clear_credentials.assert_awaited_once_with("p1")
    tool_svc.delete_tools_by_provider.assert_awaited_once_with("p1")
    provider_svc.update_provider.assert_awaited_once_with(
        "p1",
        url="https://y/mcp",
        server_status="CREATED",
        auth_type="NONE",
        auth_performer=None,
        auth_template=None,
        oauth_metadata=None,
    )


@pytest.mark.asyncio
async def test_repointing_a_merely_registered_provider_leaves_credentials_alone():
    probe = MCPProbeResult(ok=True, auth_required=False, tools=[])
    svc, _provider_svc, tool_svc = _service(probe)

    await svc.update_mcp_server(
        server_id="1000",
        body=MCPServerUpdateBody(server_url="https://y/mcp"),
        user=USER,
    )

    svc.credential_service.clear_credentials.assert_not_awaited()
    tool_svc.delete_tools_by_provider.assert_not_awaited()
