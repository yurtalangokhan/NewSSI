"""HTTP-shape tests for the MCP server admin API (plan task 8).

Services are faked via the route module's ``_*_service()`` seams; auth is
satisfied by overriding ``require_user`` with a dev user that
``require_permission`` bypasses.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import api.routes.MCPServerAdminRoute as mcp_admin_route
from app import app
from service.AuthService import AuthenticatedUser, require_user
from service.MCPCredentialService import MCPAuthError
from tests.idempotency_client import IdempotentTestClient


def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="admin@acme.io")


@pytest.fixture
def svc(monkeypatch):
    provider = AsyncMock()
    tool = AsyncMock()
    oauth = AsyncMock()
    credential = AsyncMock()
    # builtin_server_dto is a staticmethod on the real class; keep it simple.
    provider.builtin_server_dto = lambda: {"id": 1, "name": "Built-in Tools", "status": "CONNECTED"}
    monkeypatch.setattr(mcp_admin_route, "_provider_service", lambda: provider)
    monkeypatch.setattr(mcp_admin_route, "_tool_service", lambda: tool)
    monkeypatch.setattr(mcp_admin_route, "_oauth_service", lambda: oauth)
    monkeypatch.setattr(mcp_admin_route, "_credential_service", lambda: credential)
    return SimpleNamespace(provider=provider, tool=tool, oauth=oauth, credential=credential)


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = _fake_dev_user
    try:
        yield IdempotentTestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_list_servers_returns_builtin_plus_external(client, svc):
    svc.provider.list_external.return_value = [{"id": "p1", "int_id": 1000}]
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"id": 1000, "name": "GH"})
    r = client.get("/api/v1/admin/mcp/servers")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["mcp_servers"]]
    assert 1 in ids and 1000 in ids


def test_create_server_minimal_body(client, svc):
    svc.provider.create_provider.return_value = {"id": "p2", "int_id": 1001}
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"id": 1001, "name": "New"})
    r = client.post("/api/v1/admin/mcp/server", json={"name": "New", "server_url": "https://x/mcp"})
    assert r.status_code == 200
    assert r.json()["id"] == 1001
    kwargs = svc.provider.create_provider.call_args.kwargs
    assert kwargs["owner_email"] == "admin@acme.io"


def test_get_server_404_for_unknown_int_id(client, svc):
    svc.provider.get_by_int_id.return_value = None
    r = client.get("/api/v1/admin/mcp/servers/999999")
    assert r.status_code == 404


def test_status_patch_rejects_bad_enum(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    r = client.patch("/api/v1/admin/mcp/server/1000/status?status=BOGUS")
    assert r.status_code == 422


def test_tools_snapshots_sets_connected_then_returns_list(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.tool.sync_tools_from_provider.return_value = [{"id": 1000, "name": "a", "enabled": True}]
    r = client.get("/api/v1/admin/mcp/server/1000/tools/snapshots?source=mcp")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "a"
    svc.provider.set_status.assert_any_await("p1", "CONNECTED")


def test_tools_snapshots_failure_sets_disconnected_and_400(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.tool.sync_tools_from_provider.side_effect = RuntimeError("failed to reach MCP server: boom")
    r = client.get("/api/v1/admin/mcp/server/1000/tools/snapshots?source=mcp")
    assert r.status_code == 400
    svc.provider.set_status.assert_any_await("p1", "DISCONNECTED")


def test_upsert_oauth_sets_awaiting_auth(client, svc):
    svc.provider.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "name": "GH",
        "url": "https://x/mcp",
    }
    svc.provider.update_provider.return_value = {"id": "p1", "int_id": 1000}
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"is_authenticated": False})
    r = client.post(
        "/api/v1/admin/mcp/servers/create",
        json={
            "name": "GH",
            "server_url": "https://x/mcp",
            "transport": "STREAMABLE_HTTP",
            "auth_type": "OAUTH",
            "auth_performer": "PER_USER",
            "existing_server_id": 1000,
        },
    )
    assert r.status_code == 200
    assert r.json()["server_id"] == 1000
    svc.provider.set_status.assert_any_await("p1", "AWAITING_AUTH")


def test_oauth_connect_returns_url(client, svc):
    svc.provider.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "server_url": "https://x/mcp",
    }
    svc.oauth.begin.return_value = "https://as/authorize?x=1"
    r = client.post(
        "/api/v1/admin/mcp/oauth/connect",
        json={
            "server_id": "1000",
            "return_path": "/admin/actions/mcp",
            "include_resource_param": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["oauth_url"].startswith("https://as/authorize")


def test_oauth_connect_discovery_error_is_400_with_oauth_word(client, svc):
    svc.provider.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "server_url": "https://x/mcp",
    }
    svc.oauth.begin.side_effect = MCPAuthError("oauth discovery failed: nope")
    r = client.post("/api/v1/admin/mcp/oauth/connect", json={"server_id": "1000"})
    assert r.status_code == 400
    assert "oauth" in r.json()["error"]["message"]


def test_tool_status_toggle(client, svc):
    svc.tool.set_tools_enabled.return_value = 2
    r = client.patch("/api/v1/admin/tool/status", json={"tool_ids": [1000, 1001], "enabled": False})
    assert r.json() == {"updated_count": 2, "tool_ids": [1000, 1001]}


def test_delete_server_removes_provider_and_tools(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.provider.delete_provider.return_value = True
    r = client.delete("/api/v1/admin/mcp/server/1000")
    assert r.status_code == 200
    svc.provider.delete_provider.assert_awaited_with("p1")


def test_tools_snapshots_source_db_reads_cache_without_sync(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.tool.list_snapshots_for_provider.return_value = [
        {"id": 1000, "name": "cached", "enabled": True}
    ]
    r = client.get("/api/v1/admin/mcp/server/1000/tools/snapshots?source=db")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "cached"
    svc.tool.sync_tools_from_provider.assert_not_called()
    svc.tool.list_snapshots_for_provider.assert_awaited_with(1000)


def test_execute_tool_passes_arguments_through(client, svc):
    svc.tool.execute_tool.return_value = {"result": {"items": []}, "error": None}
    r = client.post(
        "/api/v1/admin/mcp/server/1000/tools/get_recent_azure_updates/execute",
        json={"arguments": {"top": 5}},
    )
    assert r.status_code == 200
    assert r.json() == {"result": {"items": []}, "error": None}
    svc.tool.execute_tool.assert_awaited_with(
        1000, "get_recent_azure_updates", {"top": 5}, user_id="dev-user"
    )


def test_execute_tool_unknown_server_is_404(client, svc):
    svc.tool.execute_tool.side_effect = ValueError("Provider 999999 not found")
    r = client.post("/api/v1/admin/mcp/server/999999/tools/x/execute", json={"arguments": {}})
    assert r.status_code == 404


def test_execute_tool_tool_error_is_200_with_error_field(client, svc):
    svc.tool.execute_tool.return_value = {"result": None, "error": "upstream 500"}
    r = client.post("/api/v1/admin/mcp/server/1000/tools/boom/execute", json={"arguments": {}})
    assert r.status_code == 200
    assert r.json()["error"] == "upstream 500"
