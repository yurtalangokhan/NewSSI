import uuid

import httpx
import pytest

from integrations import user_service_client as UserServiceClient
from tests.envelope import envelope


@pytest.mark.asyncio
async def test_get_users_by_ids_posts_once_to_internal_batch_endpoint(monkeypatch) -> None:
    from security import get_circuit_breaker
    from security.resilience import CircuitState

    get_circuit_breaker("user-service").state = CircuitState.CLOSED
    captured: dict[str, object] = {}

    async def fake_request(
        _client,
        method,
        url,
        *,
        headers,
        params=None,
        json=None,
        data=None,
        content=None,
        timeout=None,
        follow_redirects=None,
    ):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json=envelope([{"id": "owner-1", "email": "owner@example.com"}]),
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    assert await UserServiceClient.get_users_by_ids(["owner-1", "owner-2"]) == [
        {"id": "owner-1", "email": "owner@example.com"}
    ]
    assert captured["method"] == "POST"
    assert str(captured["url"]).endswith("/api/v1/internal/users/batch")
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Internal-Service-Token"]
    assert str(uuid.UUID(headers["Idempotency-Key"])) == headers["Idempotency-Key"]
    assert captured["json"] == {"user_ids": ["owner-1", "owner-2"]}
    first_key = headers["Idempotency-Key"]
    await UserServiceClient.get_users_by_ids(["owner-1", "owner-2"])
    assert captured["headers"]["Idempotency-Key"] != first_key
