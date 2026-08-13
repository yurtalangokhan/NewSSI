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
os.environ.setdefault("VALID_API_KEYS", "test-key")

from server import mcp  # noqa: E402


def test_tools_service_health_endpoint_is_public() -> None:
    app = mcp.http_app(transport="http")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tools_service_mcp_endpoint_requires_auth() -> None:
    app = mcp.http_app(transport="http")

    with TestClient(app) as client:
        response = client.post("/mcp")

    assert response.status_code in {401, 403}
