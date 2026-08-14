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
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")

from idempotency import AsyncRedisPool  # noqa: E402

from server import build_http_app, mcp  # noqa: E402


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> int:
        key = keys_and_args[0]
        token = keys_and_args[1]
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


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


def test_tools_service_mcp_post_does_not_require_idempotency_key(
    monkeypatch,
) -> None:
    redis = _FakeRedis()

    async def connect(config):
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)
    app = build_http_app()

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=initialize,
            headers={"Authorization": "Bearer test-key"},
        )

    # MCP streamable-HTTP sessions issue multiple POSTs sharing one client
    # connection, so the middleware must not 400 when no Idempotency-Key is
    # present. It passes through to the MCP handler instead.
    assert response.status_code != 400 or response.json()["error"]["code"] != (
        "idempotency_key_required"
    )
    assert "idempotency_key_required" not in response.text
