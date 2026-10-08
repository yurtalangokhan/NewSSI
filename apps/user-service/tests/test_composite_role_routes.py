"""Platform role HTTP contract: every role is addressed by its Keycloak role ID."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import roles_route
from src.controller.role_controller import CompositeRoleController
from src.repository.keycloak_role_client import catalog_cache
from src.service.coarse_role_service import RoleService
from src.service.role_service import CompositeRoleService
from tests.fakes.keycloak_roles import FakeKeycloakRoles
from tests.route_support import override_route_dependencies

CATALOG = ("user:read", "user:list", "agent:read", "tool:read")


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
    fake.ids = {
        "workspace": fake.add_client_role(
            agent, "workspace", {"agentic.permissions": ["agent:read"]}
        ),
        "tooling": fake.add_client_role(agent, "tooling", {"agentic.permissions": ["tool:read"]}),
        "manager": fake.add_realm_role(
            "manager",
            {"agentic.permissions": ["user:read"]},
            description="Managers",
        ),
        "enduser": fake.add_realm_role(
            "enduser", {"agentic.permissions": [], "agentic.builtin": ["true"]}
        ),
    }
    fake.link(fake.ids["manager"], fake.ids["workspace"])
    yield fake
    catalog_cache.clear()


@pytest.fixture
def client(monkeypatch, keycloak):
    feature_roles = RoleService()
    feature_roles.repo.client = keycloak
    service = CompositeRoleService()
    service.role_repo.client = keycloak
    service.permission_repo = SimpleNamespace(
        get_all=AsyncMock(return_value=[SimpleNamespace(name=name) for name in CATALOG])
    )
    service.user_role_repo = SimpleNamespace(list_user_ids_by_role=AsyncMock(return_value=[]))
    service.keycloak = SimpleNamespace(is_enabled=lambda: False)
    controller = object.__new__(CompositeRoleController)
    controller.service = service
    monkeypatch.setattr("src.service.role_service.get_role_service", lambda: feature_roles)
    monkeypatch.setattr(roles_route, "get_composite_role_controller", lambda: controller)
    monkeypatch.setattr("src.service.get_audit_service", lambda: SimpleNamespace(log=AsyncMock()))
    app = FastAPI()
    app.include_router(roles_route.router)
    actor = str(uuid.uuid4())
    override_route_dependencies(app, lambda: actor)
    return TestClient(app)


def test_list_exposes_keycloak_ids_under_a_single_roles_key(client, keycloak):
    body = client.get("/roles/").json()["data"]

    assert set(body) == {"roles"}
    assert {role["name"]: role["id"] for role in body["roles"]} == {
        "enduser": keycloak.ids["enduser"],
        "manager": keycloak.ids["manager"],
    }


def test_get_resolves_by_keycloak_id_and_never_by_name(client, keycloak):
    role = client.get(f"/roles/{keycloak.ids['manager']}").json()["data"]

    assert role == {
        "id": keycloak.ids["manager"],
        "name": "manager",
        "description": "Managers",
        "permissions": ["user:read"],
        "role_ids": [keycloak.ids["workspace"]],
        "role_names": ["workspace"],
        "is_builtin": False,
        "is_admin": False,
    }
    assert client.get("/roles/manager").status_code == 404
    assert client.get(f"/roles/{keycloak.ids['workspace']}").status_code == 404


def test_create_takes_a_json_body_and_returns_the_new_keycloak_id(client, keycloak):
    response = client.post(
        "/roles/",
        json={"name": "auditor", "description": "Audit", "role_ids": [keycloak.ids["tooling"]]},
    )

    assert response.status_code == 201
    created = response.json()["data"]
    assert created["id"] in keycloak.roles
    assert created["role_ids"] == [keycloak.ids["tooling"]]
    assert client.post("/roles/", json={"name": "auditor"}).status_code == 409


def test_update_takes_a_json_body_by_id(client, keycloak):
    response = client.patch(
        f"/roles/{keycloak.ids['manager']}", json={"description": "Line managers"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["description"] == "Line managers"
    assert client.patch("/roles/manager", json={"description": "x"}).status_code == 404


def test_bundles_are_linked_by_feature_role_id_only(client, keycloak):
    path = f"/roles/{keycloak.ids['manager']}/role-ids"

    response = client.put(path, json={"role_ids": [keycloak.ids["tooling"]]})

    assert response.status_code == 200
    assert response.json()["data"]["role_ids"] == [keycloak.ids["tooling"]]
    assert response.json()["data"]["role_names"] == ["tooling"]
    assert response.json()["data"]["effective_permissions"] == ["tool:read", "user:read"]
    assert client.put(path, json={"role_ids": ["tooling"]}).status_code == 400
    assert client.get(path).json()["data"]["role_ids"] == [keycloak.ids["tooling"]]


def test_attribute_free_client_role_can_be_added_to_a_composite(client, keycloak):
    rag = keycloak.add_client("rag-service")
    custom_id = keycloak.add_client_role(rag, "knowledge-tester")
    catalog_cache.clear()

    path = f"/roles/{keycloak.ids['manager']}/role-ids"
    response = client.put(path, json={"role_ids": [custom_id]})

    assert response.status_code == 200
    assert response.json()["role_ids"] == [custom_id]
    assert response.json()["role_names"] == ["knowledge-tester"]


def test_permissions_merge_direct_and_bundle_grants(client, keycloak):
    path = f"/roles/{keycloak.ids['manager']}/permissions"

    assert client.get(path).json()["data"]["permissions"] == ["agent:read", "user:read"]

    response = client.put(path, json={"permissions": ["user:list"]})
    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == ["agent:read", "user:list"]
    assert client.put(path, json={"permissions": ["nope:x"]}).status_code == 400


def test_delete_by_id_refuses_builtin_roles(client, keycloak):
    assert client.delete(f"/roles/{keycloak.ids['enduser']}").status_code == 400
    assert client.delete("/roles/manager").status_code == 404

    assert client.delete(f"/roles/{keycloak.ids['manager']}").status_code == 200
    assert keycloak.ids["manager"] not in keycloak.roles


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", "/effective-permissions"),
        ("get", "/inherited-roles"),
        ("put", "/inherited-roles"),
    ],
)
def test_alias_endpoints_are_gone(client, keycloak, method, suffix):
    response = client.request(method, f"/roles/{keycloak.ids['manager']}{suffix}", json={})
    assert response.status_code in {404, 405}


def test_compatibility_sync_endpoint_is_gone(client):
    assert client.post("/roles/sync-keycloak").status_code in {404, 405}
