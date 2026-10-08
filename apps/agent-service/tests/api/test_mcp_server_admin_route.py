"""HTTP-shape tests for the MCP server admin API (plan task 8).

Services are faked via the route module's ``_*_service()`` seams; auth is
satisfied by overriding ``require_user`` with a dev user that
``require_permission`` bypasses.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import api.routes.mcp_server_admin_route as mcp_admin_route
from api.dependencies import require_user
from app import app
from service.auth.auth_service import AuthenticatedUser
from service.mcp.mcp_credential_service import MCPAuthError
from tests.api.idempotency_client import IdempotentTestClient


@pytest.fixture(autouse=True)
def _allow_overridden_user_permissions(monkeypatch):
    """The overridden test identity is granted permissions explicitly."""
    from tests.gateway_auth import allow_all_permissions

    allow_all_permissions(monkeypatch)



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

    # The routes resolve a provider through `resolve_provider`, which for a
    # numeric id is exactly `get_by_int_id`. Delegating here keeps every test
    # below setting `get_by_int_id.return_value`, as they did before the routes
    # started accepting UUIDs as well.
    async def _resolve(server_id: str):
        if server_id.isdigit():
            return await provider.get_by_int_id(int(server_id))
        return await provider.get_provider(server_id)

    provider.resolve_provider = AsyncMock(side_effect=_resolve)
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
    ids = [s["id"] for s in r.json()["data"]["mcp_servers"]]
    assert 1 in ids and 1000 in ids


def test_create_server_minimal_body(client, svc):
    svc.provider.create_provider.return_value = {"id": "p2", "int_id": 1001}
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"id": 1001, "name": "New"})
    r = client.post("/api/v1/admin/mcp/server", json={"name": "New", "server_url": "https://x/mcp"})
    assert r.status_code == 200
    assert r.json()["data"]["id"] == 1001
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
    assert r.json()["data"][0]["name"] == "a"
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
    assert r.json()["data"]["server_id"] == 1000
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
    assert r.json()["data"]["oauth_url"].startswith("https://as/authorize")


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
    assert r.json()["data"] == {"updated_count": 2, "tool_ids": [1000, 1001]}


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
    assert r.json()["data"][0]["name"] == "cached"
    svc.tool.sync_tools_from_provider.assert_not_called()
    svc.tool.list_snapshots_for_provider.assert_awaited_with(1000)


def test_cached_tools_reads_the_database_without_touching_the_server(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.tool.list_snapshots_for_provider.return_value = [
        {"id": 1000, "name": "cached", "enabled": True}
    ]
    r = client.get("/api/v1/admin/mcp/servers/1000/tools")
    assert r.status_code == 200
    assert r.json()["data"][0]["name"] == "cached"
    svc.tool.sync_tools_from_provider.assert_not_called()
    svc.provider.set_status.assert_not_called()
    svc.tool.list_snapshots_for_provider.assert_awaited_with(1000)


def test_execute_tool_passes_arguments_through(client, svc):
    # The handler resolves the provider before executing, so the id in the path
    # can be a UUID as well as the numeric id the admin panel holds.
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000}
    svc.tool.execute_tool.return_value = {"result": {"items": []}, "error": None}
    r = client.post(
        "/api/v1/admin/mcp/server/1000/tools/get_recent_azure_updates/execute",
        json={"arguments": {"top": 5}},
    )
    assert r.status_code == 200
    assert r.json()["data"] == {"result": {"items": []}, "error": None}
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
    assert r.json()["data"]["error"] == "upstream 500"


def test_tools_snapshots_source_db_with_real_permission_check(client, svc, monkeypatch):
    """Diagnostic: exercise the real (non-dev-user) require_permission path.

    Every other test in this file overrides require_user with a "dev-user"
    identity, which require_permission's _check_permission bypasses entirely
    (``if user.user_id in ("dev-user", "internal-service"): return user``).
    That means the real AuthorizationClient.has_permission() call -- the
    thing that actually talks to user-service -- has never been exercised
    by this test file. This test uses a real-shaped user id instead, to
    check whether the route works end-to-end once permission genuinely
    resolves to True.
    """
    from api.dependencies import require_user
    from app import app
    from service.auth.auth_service import AuthenticatedUser

    real_user = AuthenticatedUser(
        user_id="11111111-1111-4111-8111-111111111111",
        email="admin@acme.io",
        access_token="real-access-token",
    )
    app.dependency_overrides[require_user] = lambda: real_user
    monkeypatch.setattr(
        "integrations.authorization_client.get_authorization_client",
        lambda: type("Fake", (), {"has_permission": AsyncMock(return_value=True)})(),
    )
    # require_permission resolves the real user-service id before checking
    # the permission (see AuthService.resolve_user_identity) -- without this,
    # real_user's UUID-shaped id makes it attempt a live, unmocked lookup
    # against user-service.
    monkeypatch.setattr(
        "service.auth.auth_service.AuthService.resolve_user_identity",
        AsyncMock(return_value={"primary_user_id": real_user.user_id}),
    )

    try:
        svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1001}
        svc.tool.list_snapshots_for_provider.return_value = [
            {"id": 1, "name": "search", "enabled": True}
        ]

        r = client.get("/api/v1/admin/mcp/server/1001/tools/snapshots?source=db")

        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_connect_binds_shared_api_token_and_syncs(client, svc):
    svc.provider.get_by_int_id.return_value = {
        "id": "p1",
        "int_id": 1000,
        "name": "GH",
        "url": "https://x/mcp",
    }
    svc.provider.update_provider.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.tool.sync_tools_from_provider.return_value = [{"id": 1000, "name": "a", "enabled": True}]
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"is_authenticated": True})

    r = client.post(
        "/api/v1/admin/mcp/servers/1000/connect",
        json={"auth_type": "API_TOKEN", "auth_performer": "ADMIN", "api_token": "secret"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["data"]["server_id"] == 1000
    svc.credential.store_admin_credentials.assert_awaited_with("p1", {"api_key": "secret"})
    svc.tool.sync_tools_from_provider.assert_awaited_with(1000, user_id="dev-user")
    svc.provider.set_status.assert_any_await("p1", "CONNECTED")


def test_connect_ignores_any_supplied_url(client, svc):
    """The connect surface must not let a caller move a provider's url."""
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.provider.update_provider.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.tool.sync_tools_from_provider.return_value = []
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"is_authenticated": True})

    r = client.post(
        "/api/v1/admin/mcp/servers/1000/connect",
        json={
            "auth_type": "NONE",
            "server_url": "http://169.254.169.254/latest/meta-data",
            "name": "hijacked",
        },
    )

    assert r.status_code == 200, r.text
    kwargs = svc.provider.update_provider.call_args.kwargs
    assert "url" not in kwargs and "name" not in kwargs


def test_connect_oauth_sets_awaiting_auth_without_sync(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.provider.update_provider.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.provider.to_mcp_server_dto = AsyncMock(return_value={"is_authenticated": False})

    r = client.post(
        "/api/v1/admin/mcp/servers/1000/connect",
        json={"auth_type": "OAUTH", "auth_performer": "PER_USER", "oauth_client_id": "cid"},
    )

    assert r.status_code == 200, r.text
    svc.provider.set_status.assert_any_await("p1", "AWAITING_AUTH")
    svc.tool.sync_tools_from_provider.assert_not_called()


def test_connect_unknown_server_is_404(client, svc):
    svc.provider.get_by_int_id.return_value = None
    r = client.post(
        "/api/v1/admin/mcp/servers/999999/connect",
        json={"auth_type": "NONE"},
    )
    assert r.status_code == 404


def test_connect_sync_failure_sets_disconnected_and_400(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.provider.update_provider.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}
    svc.tool.sync_tools_from_provider.side_effect = RuntimeError("failed to reach MCP server")

    r = client.post(
        "/api/v1/admin/mcp/servers/1000/connect",
        json={"auth_type": "NONE"},
    )

    assert r.status_code == 400
    svc.provider.set_status.assert_any_await("p1", "DISCONNECTED")


def test_disconnect_clears_credentials_and_tools_and_returns_to_catalog(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "p1", "int_id": 1000, "name": "GH", "url": "https://x/mcp"}

    r = client.delete("/api/v1/admin/mcp/servers/1000/connect")

    assert r.status_code == 200, r.text
    svc.credential.clear_credentials.assert_awaited_once_with("p1")
    svc.tool.delete_tools_by_provider.assert_awaited_once_with("p1")
    svc.provider.update_provider.assert_awaited_once_with(
        "p1",
        server_status="CREATED",
        auth_type="NONE",
        auth_performer=None,
        auth_template=None,
        oauth_metadata=None,
    )
    svc.provider.delete_provider.assert_not_awaited()


def test_disconnect_unknown_server_is_404(client, svc):
    svc.provider.get_by_int_id.return_value = None

    r = client.delete("/api/v1/admin/mcp/servers/999999/connect")

    assert r.status_code == 404
    svc.credential.clear_credentials.assert_not_awaited()


def test_connect_refuses_the_builtin_provider(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "b1", "int_id": 1, "name": "Built-in", "type": "builtin"}

    r = client.post("/api/v1/admin/mcp/servers/1/connect", json={"auth_type": "NONE"})

    assert r.status_code == 404
    svc.provider.update_provider.assert_not_awaited()


def test_disconnect_refuses_the_builtin_provider(client, svc):
    svc.provider.get_by_int_id.return_value = {"id": "b1", "int_id": 1, "name": "Built-in", "type": "builtin"}

    r = client.delete("/api/v1/admin/mcp/servers/1/connect")

    assert r.status_code == 404
    svc.tool.delete_tools_by_provider.assert_not_awaited()
    svc.credential.clear_credentials.assert_not_awaited()
