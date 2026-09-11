"""Regression coverage for agent-service connector MCP transport authentication."""

from __future__ import annotations

import os

from starlette.testclient import TestClient

os.environ.setdefault("MCP_HOST", "127.0.0.1")
os.environ.setdefault("MCP_PORT", "9000")
os.environ.setdefault("USER_SERVICE_URL", "http://user-service")
os.environ.setdefault("POSTGRES_HOST", "postgres")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "tools")
os.environ.setdefault("POSTGRES_PASSWORD", "secret")
os.environ.setdefault("POSTGRES_DB", "tools")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")

from server import build_http_app  # noqa: E402, I001


INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "agent-service-test", "version": "1.0"},
    },
}


def test_connector_mcp_transport_requires_bearer_internal_token(monkeypatch) -> None:
    internal_token = "connector-transport-secret"
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", internal_token)
    app = build_http_app()

    with TestClient(app) as client:
        rejected = client.post(
            "/mcp",
            json=INITIALIZE_REQUEST,
            headers={
                "Accept": "application/json, text/event-stream",
                "x-internal-token": internal_token,
                "x-user-id": "user-1",
            },
        )
        accepted = client.post(
            "/mcp",
            json=INITIALIZE_REQUEST,
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {internal_token}",
                "x-internal-token": internal_token,
                "x-user-id": "user-1",
                "x-binding-ref-connectors.persona_id": "persona-9",
            },
        )

    assert rejected.status_code in {401, 403}
    assert accepted.status_code == 200
    assert "initialize" not in accepted.text.lower() or '"result"' in accepted.text
