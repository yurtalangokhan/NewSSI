import httpx
import pytest

from service import UserServiceClient


@pytest.mark.asyncio
async def test_get_users_by_ids_posts_once_to_internal_batch_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_request(_client, method, url, *, headers, json):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json=[{"id": "owner-1", "email": "owner@example.com"}],
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
    assert captured["json"] == {"user_ids": ["owner-1", "owner-2"]}
