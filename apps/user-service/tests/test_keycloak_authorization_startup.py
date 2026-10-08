"""Startup provisions authorization without gateway configuration."""

from contextlib import asynccontextmanager
from copy import deepcopy
from unittest.mock import AsyncMock

from error_contract import ConfigurationError
import pytest

from src.repository.keycloak_resource_authorization import (
    ResourceAuthorizationProjectionRepository,
)


class AuthorizationClient:
    def __init__(self):
        self.details = {
            "id": "rag-id",
            "clientId": "rag-service-client",
            "publicClient": False,
            "attributes": {"keep": "value"},
        }
        self.settings = {"policyEnforcementMode": "PERMISSIVE"}
        self.policies = [
            {"id": "default-policy", "name": "Default Policy", "type": "js"},
            {"id": "default-permission", "name": "Default Permission", "type": "resource"},
            {"id": "custom-policy", "name": "custom", "type": "role"},
        ]
        self.resources = [
            {"_id": "default-resource", "name": "Default Resource"},
            {"_id": "custom-resource", "name": "custom"},
        ]
        self.writes = []

    async def clients(self):
        return [{"id": "rag-id", "clientId": "rag-service-client"}]

    async def request(self, method, path, **kwargs):
        if method != "GET":
            self.writes.append((method, path))
        if path == "/clients/rag-id":
            if method == "PUT":
                self.details = deepcopy(kwargs["json"])
            return deepcopy(self.details)
        assert self.details.get("authorizationServicesEnabled"), (
            "authorization endpoint returns 404"
        )
        if path.endswith("/resource-server"):
            if method == "PUT":
                self.settings = deepcopy(kwargs["json"])
            return deepcopy(self.settings)
        if method == "DELETE":
            identifier = path.rsplit("/", 1)[1]
            self.policies = [p for p in self.policies if p["id"] != identifier]
            self.resources = [r for r in self.resources if r["_id"] != identifier]
            return None
        if path.endswith("/policy"):
            return deepcopy(self.policies)
        if path.endswith("/resource"):
            return deepcopy(self.resources)
        raise AssertionError((method, path))


def projection_for(client):
    projection = ResourceAuthorizationProjectionRepository(client=client)

    @asynccontextmanager
    async def locked():
        yield

    projection._lock = locked
    projection.reconcile_all = AsyncMock()
    return projection


@pytest.mark.asyncio
@pytest.mark.parametrize("already_enabled", [False, True])
async def test_startup_initializes_authorization_and_removes_defaults(monkeypatch, already_enabled):
    monkeypatch.delenv("GATEWAY_KEYCLOAK_CLIENT_SECRET", raising=False)
    client = AuthorizationClient()
    client.details["authorizationServicesEnabled"] = already_enabled
    projection = projection_for(client)

    await projection.reconcile_startup()

    assert client.details["authorizationServicesEnabled"] is True
    assert client.details["attributes"] == {"keep": "value"}
    assert client.settings["policyEnforcementMode"] == "ENFORCING"
    assert client.settings["allowRemoteResourceManagement"] is False
    assert [p["name"] for p in client.policies] == ["custom"]
    assert [r["name"] for r in client.resources] == ["custom"]
    deleted = [path.rsplit("/", 1)[1] for method, path in client.writes if method == "DELETE"]
    assert deleted == ["default-permission", "default-policy", "default-resource"]
    projection.reconcile_all.assert_awaited_once()

    client.writes.clear()
    await projection.reconcile_startup()
    assert client.writes == []


@pytest.mark.asyncio
async def test_startup_does_not_convert_public_clients():
    client = AuthorizationClient()
    client.details["publicClient"] = True
    projection = projection_for(client)
    with pytest.raises(ConfigurationError):
        await projection.reconcile_startup()
    assert client.writes == []
    projection.reconcile_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_stops_when_authorization_setup_fails():
    client = AuthorizationClient()
    client.request = AsyncMock(side_effect=RuntimeError("Keycloak unavailable"))
    projection = projection_for(client)
    with pytest.raises(RuntimeError, match="Keycloak unavailable"):
        await projection.reconcile_startup()
    projection.reconcile_all.assert_not_awaited()
