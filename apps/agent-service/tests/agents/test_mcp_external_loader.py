"""Unit tests for the external-MCP runtime loader (plan task 10)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _provider(**over):
    row = {
        "id": "p1",
        "int_id": 1000,
        "name": "GH",
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "type": "external",
        "is_active": True,
        "server_status": "CONNECTED",
        "auth_type": "NONE",
        "auth_performer": None,
    }
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_disabled_flag_returns_empty(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    monkeypatch.setenv("MCP_EXTERNAL_ENABLED", "false")
    assert await load_external_mcp_tools("u1") == {}


@pytest.mark.asyncio
async def test_connected_provider_contributes_tools(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [_provider(auth_type="API_TOKEN", auth_performer="ADMIN")]
    tool = MagicMock()
    tool.name = "list_prs"
    tool.model_copy = MagicMock(side_effect=lambda update: tool)
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[tool])

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MultiServerMCPClient", return_value=client),
        patch("agents.mcp_external.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(
            return_value={"Authorization": "Bearer K"}
        )
        out = await load_external_mcp_tools("u1")

    # keyed by the server-qualified name (provider "GH" -> slug "gh")
    assert "gh__list_prs" in out
    assert "list_prs" not in out


@pytest.mark.asyncio
async def test_missing_per_user_token_skips_provider(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools
    from service.MCPCredentialService import MCPAuthError

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [_provider(auth_type="OAUTH", auth_performer="PER_USER")]

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MultiServerMCPClient") as client_ctor,
        patch("agents.mcp_external.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(
            side_effect=MCPAuthError("oauth authorization required")
        )
        out = await load_external_mcp_tools("u1")

    assert out == {}
    client_ctor.assert_not_called()


@pytest.mark.asyncio
async def test_same_tool_name_on_two_servers_stays_distinct(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [
        _provider(id="a", int_id=1000, name="Alpha"),
        _provider(id="b", int_id=1001, name="Beta"),
    ]

    def _client_for(conn_map):
        slug = next(iter(conn_map))
        t = MagicMock()
        t.name = "search"
        t.model_copy = MagicMock(side_effect=lambda update: update)  # returns {"name": qualified}
        c = MagicMock()
        c.get_tools = AsyncMock(return_value=[t])
        c._slug = slug
        return c

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MultiServerMCPClient", side_effect=_client_for),
        patch("agents.mcp_external.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        out = await load_external_mcp_tools("u1")

    assert set(out) == {"alpha__search", "beta__search"}


@pytest.mark.asyncio
async def test_qualified_collision_keeps_first(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [_provider(name="Alpha")]
    t1 = MagicMock()
    t1.name = "search"
    t1.model_copy = MagicMock(side_effect=lambda update: t1)
    t2 = MagicMock()
    t2.name = "search"
    t2.model_copy = MagicMock(side_effect=lambda update: t2)
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[t1, t2])

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MultiServerMCPClient", return_value=client),
        patch("agents.mcp_external.MCPCredentialService") as cs,
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        out = await load_external_mcp_tools("u1")

    assert list(out) == ["alpha__search"]
    assert out["alpha__search"] is t1


@pytest.mark.asyncio
async def test_wanted_names_filters_providers(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [_provider()]
    tool_repo = AsyncMock()
    tool_repo.list_by_provider.return_value = [{"name": "unrelated_tool", "enabled": True}]

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MCPToolRepository", return_value=tool_repo),
        patch("agents.mcp_external.MultiServerMCPClient") as client_ctor,
    ):
        # wanted_names are qualified; the provider's cached tool qualifies to
        # "gh__unrelated_tool", which does not intersect -> provider skipped.
        out = await load_external_mcp_tools("u1", wanted_names={"gh__list_prs"})

    client_ctor.assert_not_called()
    assert out == {}


@pytest.mark.asyncio
async def test_non_connected_providers_ignored(monkeypatch):
    from agents.mcp_external import load_external_mcp_tools

    prov_repo = AsyncMock()
    prov_repo.list_all.return_value = [
        _provider(server_status="AWAITING_AUTH"),
        _provider(type="builtin"),
    ]

    with (
        patch("agents.mcp_external.MCPProviderRepository", return_value=prov_repo),
        patch("agents.mcp_external.MultiServerMCPClient") as client_ctor,
    ):
        out = await load_external_mcp_tools("u1")

    client_ctor.assert_not_called()
    assert out == {}
