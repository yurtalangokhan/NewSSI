"""Feature role HTTP contract: every bundle is addressed by its Keycloak role ID."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import coarse_roles_route
from src.controller.coarse_role_controller import RoleController
from src.repository.keycloak_role_client import catalog_cache
from src.service.coarse_role_service import RoleService
from tests.fakes.keycloak_roles import FakeKeycloakRoles
from tests.route_support import override_route_dependencies

CATALOG = ("agent:read", "agent:list", "rag:read")


@pytest.fixture
def keycloak(monkeypatch):
    catalog_cache.clear()
    client_ids = SimpleNamespace(
        KEYCLOAK_AGENT_SERVICE_CLIENT_ID="agent-service",
        KEYCLOAK_RAG_SERVICE_CLIENT_ID="rag-service",
        KEYCLOAK_TOOLS_SERVICE_CLIENT_ID="tools-service",
        KEYCLOAK_USER_SERVICE_CLIENT_ID="user-service",
    )
    monkeypatch.setattr("src.repository.keycloak_role_client.env", client_ids)
    fake = FakeKeycloakRoles()
    agent = fake.add_client("agent-service")
    rag = fake.add_client("rag-service")
    fake.ids = {
        "agent-reader": fake.add_client_role(
            agent, "reader", {"agentic.permissions": ["agent:read"]}
        ),
        "rag-reader": fake.add_client_role(rag, "reader", {"agentic.permissions": ["rag:read"]}),
        "enduser": fake.add_realm_role("enduser"),
    }
    yield fake
    catalog_cache.clear()


@pytest.fixture
def client(monkeypatch, keycloak):
    service = RoleService()
    service.repo.client = keycloak
    service.permission_repo = SimpleNamespace(
        get_all=AsyncMock(return_value=[SimpleNamespace(name=name) for name in CATALOG])
    )
    controller = object.__new__(RoleController)
    controller.service = service
    monkeypatch.setattr(coarse_roles_route, "get_role_controller", lambda: controller)
    monkeypatch.setattr("src.service.get_audit_service", lambda: SimpleNamespace(log=AsyncMock()))
    app = FastAPI()
    app.include_router(coarse_roles_route.router)
    actor = str(uuid.uuid4())
    override_route_dependencies(app, lambda: actor)
    return TestClient(app)


def test_same_name_on_two_clients_is_addressed_by_id(client, keycloak):
    agent = client.get(f"/coarse-roles/{keycloak.ids['agent-reader']}").json()["data"]
    rag = client.get(f"/coarse-roles/{keycloak.ids['rag-reader']}").json()["data"]

    assert agent == {
        "id": keycloak.ids["agent-reader"],
        "name": "reader",
        "description": "",
        "service_client": "agent-service",
        "permissions": ["agent:read"],
        "is_builtin": False,
    }
    assert rag["service_client"] == "rag-service"
    assert client.get("/coarse-roles/reader").status_code == 404
    assert client.get(f"/coarse-roles/{keycloak.ids['enduser']}").status_code == 404


def test_create_takes_a_json_body_and_is_unique_per_client(client, keycloak):
    body = {"name": "writer", "service_client": "agent-service", "permissions": ["agent:list"]}

    response = client.post("/coarse-roles/", json=body)

    assert response.status_code == 201
    assert response.json()["data"]["id"] in keycloak.roles
    assert client.post("/coarse-roles/", json=body).status_code == 409
    assert (
        client.post("/coarse-roles/", json={**body, "service_client": "rag-service"}).status_code
        == 201
    )
    assert (
        client.post("/coarse-roles/", json={**body, "name": "x", "permissions": ["nope"]})
    ).status_code == 400


def test_update_and_permissions_address_the_role_by_id(client, keycloak):
    role_id = keycloak.ids["agent-reader"]

    assert (
        client.patch(f"/coarse-roles/{role_id}", json={"description": "A"}).json()["data"]["description"]
        == "A"
    )
    response = client.put(
        f"/coarse-roles/{role_id}/permissions", json={"permissions": ["agent:list"]}
    )
    assert response.json()["data"] == {"id": role_id, "name": "reader", "permissions": ["agent:list"]}
    assert client.get(f"/coarse-roles/{role_id}/permissions").json()["data"]["permissions"] == [
        "agent:list"
    ]
    assert client.patch("/coarse-roles/reader", json={"description": "x"}).status_code == 404
    assert (
        client.put(
            f"/coarse-roles/{role_id}/permissions", json={"permissions": ["nope"]}
        ).status_code
        == 400
    )


def test_delete_by_id(client, keycloak):
    assert client.delete("/coarse-roles/reader").status_code == 404
    assert client.delete(f"/coarse-roles/{keycloak.ids['rag-reader']}").status_code == 200
    assert keycloak.ids["rag-reader"] not in keycloak.roles


def test_builtin_feature_bundle_cannot_be_deleted(client, keycloak):
    rag = next(c["id"] for c in keycloak.clients_by_id.values() if c["clientId"] == "rag-service")
    builtin_id = keycloak.add_client_role(
        rag, "knowledge-admin", {"agentic.permissions": [], "agentic.builtin": ["true"]}
    )
    catalog_cache.clear()

    assert client.get(f"/coarse-roles/{builtin_id}").json()["is_builtin"] is True
    assert client.delete(f"/coarse-roles/{builtin_id}").status_code == 400
    assert builtin_id in keycloak.roles


def test_attribute_free_keycloak_client_role_can_be_listed_and_deleted(client, keycloak):
    rag = next(c["id"] for c in keycloak.clients_by_id.values() if c["clientId"] == "rag-service")
    role_id = keycloak.add_client_role(rag, "knowledge-tester")
    catalog_cache.clear()

    response = client.get("/coarse-roles/")
    custom = next(role for role in response.json()["roles"] if role["id"] == role_id)
    assert custom["name"] == "knowledge-tester"
    assert custom["permissions"] == []
    assert custom["is_builtin"] is False
    assert client.delete(f"/coarse-roles/{role_id}").status_code == 200
    assert role_id not in keycloak.roles


def test_aggregated_permissions_take_feature_role_ids(client, keycloak):
    ids = f"{keycloak.ids['agent-reader']},{keycloak.ids['rag-reader']},reader"

    response = client.get("/coarse-roles/aggregated/", params={"ids": ids})

    assert response.json()["data"] == {"permissions": ["agent:read", "rag:read"]}
    assert client.get("/coarse-roles/aggregated/", params={"names": "reader"}).status_code == 422


def test_service_clients_are_listed(client):
    assert client.get("/coarse-roles/service-clients/list").json()["data"] == {
        "service_clients": ["agent-service", "rag-service"]
    }
