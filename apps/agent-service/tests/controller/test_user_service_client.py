import pytest

from service import UserServiceClient


@pytest.mark.asyncio
async def test_get_user_by_keycloak_id_skips_dev_placeholder(monkeypatch) -> None:
    async def fail_request(*args, **kwargs):
        raise AssertionError("dev placeholder should not call user-service")

    UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE.clear()
    monkeypatch.setattr(UserServiceClient, "_request", fail_request)

    assert await UserServiceClient.get_user_by_keycloak_id("user-1") is None


@pytest.mark.asyncio
async def test_get_user_by_keycloak_id_caches_lookup(monkeypatch) -> None:
    calls = 0

    async def fake_request(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"id": "local-user-id"}

    UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE.clear()
    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    keycloak_id = "11111111-1111-4111-8111-111111111111"

    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {"id": "local-user-id"}
    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {"id": "local-user-id"}
    assert calls == 1


@pytest.mark.asyncio
async def test_user_service_client_uses_api_v1_internal_permission_path(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"permissions": ["chat:read"]}

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    assert await UserServiceClient.get_user_permissions("user-1") == {
        "permissions": ["chat:read"]
    }
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/v1/internal/users/user-1/permissions"
    assert captured["kwargs"]["include_internal_token"] is True


@pytest.mark.asyncio
async def test_user_service_client_uses_api_v1_internal_keycloak_upsert_path(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_request(method, path, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["kwargs"] = kwargs
        return {"id": "local-user-id"}

    monkeypatch.setattr(UserServiceClient, "_request", fake_request)

    assert await UserServiceClient.upsert_user_from_keycloak(
        keycloak_id="keycloak-id",
        email="user@example.com",
    ) == {"id": "local-user-id"}
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/internal/users/upsert-from-keycloak"
    assert captured["kwargs"] == {
        "json_body": {
            "keycloak_id": "keycloak-id",
            "email": "user@example.com",
            "first_name": None,
            "last_name": None,
            "username": None,
        },
        "access_token": None,
        "include_internal_token": True,
    }
