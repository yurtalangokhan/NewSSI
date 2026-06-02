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

    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {
        "id": "local-user-id"
    }
    assert await UserServiceClient.get_user_by_keycloak_id(keycloak_id) == {
        "id": "local-user-id"
    }
    assert calls == 1
