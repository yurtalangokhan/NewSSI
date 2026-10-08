"""Feature bundles are Keycloak client roles identified only by their Keycloak ID."""

import dataclasses
from types import SimpleNamespace

from error_contract import BadRequestError
import pytest

from src.repository.coarse_role_repository import RoleRepository
from src.repository.keycloak_role_client import CoarseRoleRecord, catalog_cache
from tests.fakes.keycloak_roles import FakeKeycloakRoles


@pytest.fixture
def keycloak(monkeypatch):
    catalog_cache.clear()
    monkeypatch.setattr(
        "src.repository.keycloak_role_client.env",
        SimpleNamespace(
            KEYCLOAK_AGENT_SERVICE_CLIENT_ID="agent-service",
            KEYCLOAK_RAG_SERVICE_CLIENT_ID="rag-service",
            KEYCLOAK_TOOLS_SERVICE_CLIENT_ID="tools-service",
            KEYCLOAK_USER_SERVICE_CLIENT_ID="user-service",
        ),
    )
    fake = FakeKeycloakRoles()
    yield fake
    catalog_cache.clear()


@pytest.fixture
def repo(keycloak):
    repository = RoleRepository()
    repository.client = keycloak
    return repository


def _seed_duplicate_names(keycloak):
    agent = keycloak.add_client("agent-service")
    rag = keycloak.add_client("rag-service")
    agent_role = keycloak.add_client_role(agent, "reader", {"agentic.permissions": ["agent:read"]})
    rag_role = keycloak.add_client_role(rag, "reader", {"agentic.permissions": ["rag:read"]})
    return agent_role, rag_role


@pytest.mark.asyncio
async def test_get_by_id_returns_the_keycloak_identity_of_the_client_role(repo, keycloak):
    agent_role, _ = _seed_duplicate_names(keycloak)

    role = await repo.get_by_id(agent_role)

    assert role == CoarseRoleRecord(
        id=agent_role,
        name="reader",
        description="",
        service_client="agent-service",
        permissions=("agent:read",),
        is_builtin=False,
    )


@pytest.mark.asyncio
async def test_feature_bundle_protection_uses_keycloak_attribute(repo, keycloak):
    client = keycloak.add_client("rag-service")
    builtin_id = keycloak.add_client_role(
        client, "renamed-bundle", {"agentic.permissions": [], "agentic.builtin": ["true"]}
    )
    unmarked_id = keycloak.add_client_role(client, "knowledge-admin", {"agentic.permissions": []})
    explicitly_custom_id = keycloak.add_client_role(
        client,
        "knowledge-manager",
        {"agentic.permissions": [], "agentic.builtin": ["false"]},
    )

    assert (await repo.get_by_id(builtin_id)).is_builtin is True
    assert (await repo.get_by_id(unmarked_id)).is_builtin is False
    assert (await repo.get_by_id(explicitly_custom_id)).is_builtin is False

    created = await repo.create("knowledge-tester", "rag-service")
    assert created.is_builtin is False
    assert "agentic.builtin" not in keycloak.roles[created.id]["attributes"]


@pytest.mark.asyncio
async def test_attribute_free_client_role_is_a_custom_feature_bundle(repo, keycloak):
    client = keycloak.add_client("rag-service")
    keycloak.add_client_role(client, "keycloak-internal")
    custom_id = keycloak.add_client_role(client, "knowledge-tester")
    internal_id = keycloak.add_client_role(client, "uma_protection")

    custom = await repo.get_by_id(custom_id)
    assert custom.name == "knowledge-tester"
    assert custom.permissions == ()
    assert custom.is_builtin is False
    assert await repo.get_by_id(internal_id) is None
    assert {role.name for role in await repo.get_all()} == {
        "keycloak-internal",
        "knowledge-tester",
    }


@pytest.mark.asyncio
async def test_same_name_on_two_clients_is_resolved_unambiguously_by_id(repo, keycloak):
    agent_role, rag_role = _seed_duplicate_names(keycloak)

    roles = await repo.get_by_ids([rag_role, agent_role])

    assert [(r.id, r.service_client) for r in roles] == [
        (rag_role, "rag-service"),
        (agent_role, "agent-service"),
    ]


@pytest.mark.asyncio
async def test_names_and_realm_role_ids_are_not_feature_role_ids(repo, keycloak):
    _seed_duplicate_names(keycloak)
    realm_role = keycloak.add_realm_role("enduser")

    assert await repo.get_by_id("reader") is None
    assert await repo.get_by_id(realm_role) is None
    assert await repo.get_by_ids(["reader", realm_role]) == []


@pytest.mark.asyncio
async def test_permissions_are_expanded_per_requested_id(repo, keycloak):
    agent_role, rag_role = _seed_duplicate_names(keycloak)

    permissions = await repo.get_permissions_by_ids([agent_role, rag_role, "unknown"])

    assert permissions == {agent_role: ["agent:read"], rag_role: ["rag:read"]}


@pytest.mark.asyncio
async def test_update_and_delete_address_the_role_by_id(repo, keycloak):
    agent_role, rag_role = _seed_duplicate_names(keycloak)

    updated = await repo.update(agent_role, description="Agents", permissions=["agent:list"])
    assert (updated.description, updated.permissions) == ("Agents", ("agent:list",))
    assert (await repo.get_by_id(rag_role)).permissions == ("rag:read",)

    assert await repo.delete(agent_role) is True
    assert await repo.get_by_id(agent_role) is None
    assert await repo.delete(agent_role) is False
    assert await repo.update(agent_role, description="gone") is None


@pytest.mark.asyncio
async def test_moving_a_role_to_another_client_is_rejected(repo, keycloak):
    agent_role, _ = _seed_duplicate_names(keycloak)

    with pytest.raises(BadRequestError):
        await repo.update(agent_role, service_client="rag-service")


@pytest.mark.asyncio
async def test_create_returns_the_server_assigned_id_and_name_is_unique_per_client(repo, keycloak):
    _seed_duplicate_names(keycloak)

    created = await repo.create("writer", "agent-service", permissions=["agent:update"])

    assert created.id in keycloak.roles
    assert created.service_client == "agent-service"
    assert await repo.exists("reader", "agent-service") is True
    assert await repo.exists("writer", "rag-service") is False


def test_record_is_immutable():
    record = CoarseRoleRecord(
        id="1", name="n", description=None, service_client="agent-service", permissions=()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.name = "other"
