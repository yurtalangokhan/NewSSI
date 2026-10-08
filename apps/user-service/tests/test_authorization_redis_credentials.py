from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest


@pytest.mark.parametrize("secret", ["redis-password", None])
@pytest.mark.parametrize("role_write", [False, True])
async def test_authorization_redis_uses_password(monkeypatch, secret, role_write):
    import redis.asyncio

    from src.repository import keycloak_authorization as auth
    from src.repository import keycloak_resource_authorization as projection
    from src.repository import keycloak_role_client as roles

    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("KEYCLOAK_REALM", "test")
    if secret is None:
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("REDIS_PASSWORD", secret)
    observed = {}

    @asynccontextmanager
    async def redis_client(**kwargs):
        observed.update(kwargs)
        yield object()

    @asynccontextmanager
    async def lock(*args):
        yield

    monkeypatch.setattr(redis.asyncio, "Redis", redis_client)
    monkeypatch.setattr(auth, "policy_write_lock", lock)
    monkeypatch.setattr(projection, "policy_write_lock", lock)
    if role_write:
        monkeypatch.setattr(auth, "clear_feature_grants", AsyncMock())
        monkeypatch.setattr(auth, "reconcile", AsyncMock())
        client = roles.KeycloakRoleClient()
        monkeypatch.setattr(client, "_request", AsyncMock())
        await client.request("POST", "/roles")
    else:
        async with projection.ResourceAuthorizationProjectionRepository()._lock():
            pass
    assert observed["password"] == ("redis-password" if secret else None)
