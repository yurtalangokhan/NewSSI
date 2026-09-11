"""HTTP-shape tests for the MCP OAuth callback endpoint (plan task 9)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import api.routes.MCPOAuthCallbackRoute as callback_route
from app import app
from service.AuthService import AuthenticatedUser, require_user
from service.MCPCredentialService import MCPAuthError
from tests.idempotency_client import IdempotentTestClient


def _fake_dev_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="dev-user", email="admin@acme.io")


@pytest.fixture
def oauth_svc(monkeypatch):
    svc = AsyncMock()
    monkeypatch.setattr(callback_route, "_oauth_service", lambda: svc)
    return svc


@pytest.fixture
def client():
    app.dependency_overrides[require_user] = _fake_dev_user
    try:
        yield IdempotentTestClient(app)
    finally:
        app.dependency_overrides.pop(require_user, None)


def test_callback_completes(client, oauth_svc):
    oauth_svc.complete.return_value = {"redirect_url": "/admin/actions/mcp", "server_name": "GH"}
    r = client.post("/api/v1/mcp/oauth/callback?code=abc&state=st")
    assert r.status_code == 200
    assert r.json() == {"redirect_url": "/admin/actions/mcp", "server_name": "GH"}
    oauth_svc.complete.assert_awaited_with("st", "abc")


def test_callback_missing_params_is_400(client, oauth_svc):
    r = client.post("/api/v1/mcp/oauth/callback")
    assert r.status_code == 400


def test_callback_expired_state_maps_to_400_oauth(client, oauth_svc):
    oauth_svc.complete.side_effect = MCPAuthError("oauth session not found or expired")
    r = client.post("/api/v1/mcp/oauth/callback?code=abc&state=st")
    assert r.status_code == 400
    assert "oauth" in r.json()["error"]["message"]


def test_callback_reads_state_from_json_body(client, oauth_svc):
    oauth_svc.complete.return_value = {"redirect_url": "/app", "server_name": "X"}
    r = client.post(
        "/api/v1/mcp/oauth/callback",
        json={"code": "c2", "state": "s2", "transport": "streamable-http"},
    )
    assert r.status_code == 200
    oauth_svc.complete.assert_awaited_with("s2", "c2")
