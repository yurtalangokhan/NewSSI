"""Unit tests for MCPToolService authenticated sync + ToolSnapshot (plan task 6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from error_contract import DependencyUnavailableError, NotFoundError
import pytest


def _service():
    from service.mcp.mcp_tool_service import MCPToolService

    return MCPToolService(tool_repo=AsyncMock(), provider_repo=AsyncMock())


def test_to_tool_snapshot_shape():
    svc = _service()
    snap = svc.to_tool_snapshot(
        {"int_id": 1000, "name": "list_prs", "description": "List PRs", "enabled": True},
        {"int_id": 10000, "auth_type": "OAUTH"},
    )
    assert snap["id"] == 1000
    assert snap["mcp_server_id"] == 10000
    assert snap["enabled"] is True
    assert snap["passthrough_auth"] is False
    assert snap["display_name"] == "list_prs"
    assert set(snap) >= {
        "id",
        "name",
        "display_name",
        "description",
        "definition",
        "custom_headers",
        "in_code_tool_id",
        "passthrough_auth",
        "oauth_config_id",
        "oauth_config_name",
        "mcp_server_id",
        "user_id",
        "enabled",
        "chat_selectable",
        "agent_creation_selectable",
        "default_enabled",
    }


def test_to_tool_snapshot_passthrough_auth_for_pt_oauth():
    svc = _service()
    snap = svc.to_tool_snapshot(
        {"int_id": 1, "name": "t", "description": "", "enabled": True},
        {"int_id": 2, "auth_type": "PT_OAUTH"},
    )
    assert snap["passthrough_auth"] is True


@pytest.mark.asyncio
async def test_sync_uses_resolved_auth_headers_and_upserts():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "API_TOKEN",
        "auth_performer": "ADMIN",
    }
    svc._tool_repo.bulk_upsert = AsyncMock(return_value=2)
    svc._tool_repo.list_by_provider = AsyncMock(
        return_value=[
            {"int_id": 1000, "name": "a", "description": "", "enabled": True},
            {"int_id": 1001, "name": "b", "description": "", "enabled": True},
        ]
    )

    fake_tool = MagicMock()
    fake_tool.name = "a"
    fake_tool.description = ""
    fake_tool.args_schema = {"type": "object"}
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[fake_tool])

    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(
            return_value={"Authorization": "Bearer K"}
        )
        out = await svc.sync_tools_from_provider(1000, user_id="u1")

    cs.get_instance.return_value.resolve_headers.assert_awaited_once()
    svc._tool_repo.bulk_upsert.assert_awaited_once()
    assert [o["name"] for o in out] == ["a", "b"]
    assert out[0]["mcp_server_id"] == 1000


@pytest.mark.asyncio
async def test_sync_accepts_uuid_string_and_defaults_user_none():
    svc = _service()
    svc._provider_repo.get_by_id.return_value = {
        "id": "11111111-1111-1111-1111-111111111111",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
        "auth_performer": None,
    }
    svc._tool_repo.bulk_upsert = AsyncMock(return_value=0)
    svc._tool_repo.list_by_provider = AsyncMock(return_value=[])

    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[])
    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        out = await svc.sync_tools_from_provider("11111111-1111-1111-1111-111111111111")

    svc._provider_repo.get_by_id.assert_awaited_once()
    assert out == []


@pytest.mark.asyncio
async def test_sync_reports_connection_failure_as_dependency_unavailable():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
    }
    client = MagicMock()
    client.get_tools = AsyncMock(side_effect=RuntimeError("boom"))
    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        with pytest.raises(DependencyUnavailableError) as ei:
            await svc.sync_tools_from_provider(1000, user_id="u1")
    # The upstream diagnostic never reaches the caller.
    assert "boom" not in str(ei.value)


@pytest.mark.asyncio
async def test_set_tools_enabled_delegates_to_repo():
    svc = _service()
    svc._tool_repo.set_enabled = AsyncMock(return_value=2)
    assert await svc.set_tools_enabled([1000, 1001], False) == 2
    svc._tool_repo.set_enabled.assert_awaited_with([1000, 1001], False)


def test_to_tool_snapshot_includes_input_schema():
    svc = _service()
    snap = svc.to_tool_snapshot(
        {
            "int_id": 1,
            "name": "t",
            "description": "",
            "enabled": True,
            "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
        {"int_id": 2, "auth_type": "NONE"},
    )
    assert snap["input_schema"] == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }


def test_to_tool_snapshot_input_schema_defaults_empty():
    svc = _service()
    snap = svc.to_tool_snapshot(
        {"int_id": 1, "name": "t", "description": "", "enabled": True},
        {"int_id": 2, "auth_type": "NONE"},
    )
    assert snap["input_schema"] == {}


@pytest.mark.asyncio
async def test_execute_tool_happy_path():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
    }
    tool = MagicMock()
    tool.name = "do_thing"
    tool.ainvoke = AsyncMock(return_value={"ok": True})
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[tool])
    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        out = await svc.execute_tool(1000, "do_thing", {"a": 1}, user_id="u1")
    tool.ainvoke.assert_awaited_with({"a": 1})
    assert out == {"result": {"ok": True}, "error": None}


@pytest.mark.asyncio
async def test_execute_tool_unknown_tool_is_reported_as_not_found():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
    }
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[])
    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        with pytest.raises(NotFoundError):
            await svc.execute_tool(1000, "missing", {}, user_id="u1")


@pytest.mark.asyncio
async def test_execute_tool_invoke_failure_is_captured():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "url": "https://x/mcp",
        "transport": "streamable_http",
        "auth_type": "NONE",
    }
    tool = MagicMock()
    tool.name = "boom"
    tool.ainvoke = AsyncMock(side_effect=RuntimeError("upstream 500"))
    client = MagicMock()
    client.get_tools = AsyncMock(return_value=[tool])
    with (
        patch("service.mcp.mcp_tool_service.MultiServerMCPClient", return_value=client),
        patch("service.mcp.mcp_tool_service.MCPCredentialService") as cs,
        patch("service.mcp.mcp_tool_service.validate_mcp_server_url", AsyncMock(return_value=None)),
    ):
        cs.get_instance.return_value.resolve_headers = AsyncMock(return_value={})
        out = await svc.execute_tool(1000, "boom", {}, user_id="u1")
    assert out["result"] is None
    assert out["error"] == "Internal server error"
    assert "upstream 500" not in out["error"]


@pytest.mark.asyncio
async def test_execute_tool_unknown_provider_is_reported_as_not_found():
    svc = _service()
    svc._provider_repo.get_by_int_id.return_value = None
    with pytest.raises(NotFoundError):
        await svc.execute_tool(999999, "x", {}, user_id="u1")


def test_qualify_mcp_tool_name_slugs_server_name():
    from service.mcp.mcp_tool_service import qualify_mcp_tool_name

    assert (
        qualify_mcp_tool_name({"name": "Microsoft Release Communications"}, "get_x")
        == "microsoft_release_communications__get_x"
    )
    assert qualify_mcp_tool_name({"name": ""}, "t") == "mcp__t"


def test_to_tool_snapshot_includes_qualified_name():
    svc = _service()
    snap = svc.to_tool_snapshot(
        {"int_id": 1, "name": "ask_question", "description": "", "enabled": True},
        {"int_id": 2, "name": "DeepWiki", "auth_type": "NONE"},
    )
    assert snap["name"] == "ask_question"
    assert snap["display_name"] == "ask_question"
    assert snap["qualified_name"] == "deepwiki__ask_question"
