"""The role distribution endpoint answers at once, even while Keycloak is slow."""

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes import user_route
from src.service import role_distribution
from tests.route_support import override_route_dependencies


@pytest.fixture
def slow_directory(monkeypatch):
    release = asyncio.Event()

    async def count_by_role(self):
        await release.wait()
        return [{"role": "enduser", "count": 2}]

    monkeypatch.setattr("src.repository.UserRepository.count_by_role", count_by_role)
    monkeypatch.setattr(role_distribution, "_snapshot", None)
    return release


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(user_route.router)
    actor = str(uuid.uuid4())
    override_route_dependencies(app, lambda: actor)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_cold_distribution_is_pending_immediately_then_ready(slow_directory, client):
    async with client:
        pending = await asyncio.wait_for(client.get("/users/role-distribution"), timeout=1)
        assert pending.status_code == 200
        assert pending.json()["data"] == {"status": "pending", "distribution": [], "computed_at": None}

        slow_directory.set()
        for _ in range(10):
            await asyncio.sleep(0)
        ready = (await client.get("/users/role-distribution")).json()["data"]

    assert ready["status"] == "ready"
    assert ready["distribution"] == [{"role": "enduser", "count": 2}]
    assert ready["computed_at"]
