from idempotency import AsyncRedisPool  # noqa: E402


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

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                deleted += 1
        return deleted


def test_tools_service_health_endpoint_is_public(http_client) -> None:
    response = http_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tools_service_readiness_endpoint_is_public(http_client) -> None:
    response = http_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["service"] == "tools-service"


def test_tools_service_readiness_returns_503_when_required_dependency_fails(http_client) -> None:
    from src.core.observability import DependencyPolicy, DependencyStatus, dependency_registry

    dependency_registry.record(
        DependencyStatus(
            name="postgres",
            policy=DependencyPolicy.REQUIRED,
            status="failed",
        )
    )
    try:
        response = http_client.get("/health/ready")
    finally:
        dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"]["postgres"]["status"] == "failed"
    assert response.json()["dependencies"]["postgres"]["required"] is True


def test_tools_service_mcp_endpoint_requires_auth(http_client) -> None:
    response = http_client.post("/mcp")

    assert response.status_code in {401, 403}


def test_tools_service_mcp_post_does_not_require_idempotency_key(monkeypatch, http_client) -> None:
    redis = _FakeRedis()

    async def connect(config):
        return redis

    monkeypatch.setattr(AsyncRedisPool, "connect", connect)

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

    response = http_client.post(
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
