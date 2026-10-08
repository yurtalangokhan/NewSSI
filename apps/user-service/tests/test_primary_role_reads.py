import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.repository.keycloak_role_client import PRIMARY_ROLE
from src.repository.user_role_repository import UserRoleRepository


@pytest.fixture
def pooled(monkeypatch):
    scopes = []

    class Admin:
        @asynccontextmanager
        async def admin_request_scope(self):
            scopes.append("open")
            yield
            scopes.append("closed")

    monkeypatch.setattr("src.service.keycloak_service.get_keycloak_service", lambda: Admin())
    return scopes


async def test_primary_reads_only_profile_and_effective_roles_in_bounded_waves(pooled):
    ids = [uuid.UUID(int=i + 1) for i in range(19)]
    active = peak = 0
    calls = []

    async def request(method, path, **kwargs):
        nonlocal active, peak
        assert method == "GET" and pooled == ["open"]
        calls.append(path)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        if path.endswith("/composite"):
            return [{"name": "enduser"}, {"name": "Unit Manager"}]
        assert path.count("/") == 2, "Direct mappings must not be read"
        return {"attributes": {PRIMARY_ROLE: ["Unit Manager"]}}

    repo = UserRoleRepository()
    repo.client = SimpleNamespace(request=request)
    assert await repo.get_primary_roles(ids + ids[:2]) == dict.fromkeys(ids, "Unit Manager")
    assert len(calls) == 38 and peak == 8 and active == 0
    assert pooled == ["open", "closed"]


async def test_primary_lookup_preserves_missing_empty_and_fallback_semantics(pooled):
    profiles = {
        "missing": None,
        "empty": {},
        "fallback": {},
        "stale": {"attributes": {PRIMARY_ROLE: ["removed"]}},
    }
    roles = {
        "empty": [{"name": "offline_access"}],
        "fallback": [{"name": "Z"}, {"name": "A"}],
        "stale": [{"name": "enduser"}, {"name": "system-admin"}],
    }

    async def request(method, path, **kwargs):
        identity = path.split("/")[2]
        return roles[identity] if path.endswith("/composite") else profiles[identity]

    repo = UserRoleRepository()
    repo.client = SimpleNamespace(request=AsyncMock(side_effect=request))
    assert await repo.get_primary_roles(profiles) == {"fallback": "A", "stale": "system-admin"}
    assert repo.client.request.await_count == 7


async def test_primary_lookup_drains_failed_wave_and_stops(pooled):
    active = calls = 0

    async def request(method, path, **kwargs):
        nonlocal active, calls
        active += 1
        calls += 1
        await asyncio.sleep(0)
        active -= 1
        raise ValueError("Unavailable")

    repo = UserRoleRepository()
    repo.client = SimpleNamespace(request=request)
    with pytest.raises(ValueError, match="Unavailable"):
        await repo.get_primary_roles(range(20))
    assert calls == 8 and active == 0
