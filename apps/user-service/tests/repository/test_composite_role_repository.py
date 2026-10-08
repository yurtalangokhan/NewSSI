"""Platform roles are Keycloak realm roles identified only by their Keycloak ID."""

import dataclasses
from types import SimpleNamespace

from error_contract import BadRequestError
import pytest

from src.repository.keycloak_role_client import CompositeRoleRecord, catalog_cache
from src.repository.role_repository import CompositeRoleRepository
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
    repository = CompositeRoleRepository()
    repository.client = keycloak
    return repository


@pytest.fixture
def catalog(keycloak):
    agent = keycloak.add_client("agent-service")
    infrastructure = keycloak.add_client("realm-management")
    bundle = keycloak.add_client_role(agent, "workspace", {"agentic.permissions": ["agent:read"]})
    other = keycloak.add_client_role(agent, "tooling", {"agentic.permissions": ["tool:read"]})
    infra_role = keycloak.add_client_role(infrastructure, "view-users")
    manager = keycloak.add_realm_role(
        "manager",
        {"agentic.permissions": ["user:read"], "agentic.builtin": ["true"]},
        description="Managers",
    )
    keycloak.link(manager, bundle, infra_role)
    return {"manager": manager, "bundle": bundle, "other": other, "infra": infra_role}


@pytest.mark.asyncio
async def test_get_by_id_exposes_the_keycloak_id_and_service_client_bundles(repo, catalog):
    role = await repo.get_by_id(catalog["manager"])

    assert role == CompositeRoleRecord(
        id=catalog["manager"],
        name="manager",
        description="Managers",
        permissions=("user:read",),
        bundle_ids=(catalog["bundle"],),
        bundle_names=("workspace",),
        is_builtin=True,
    )


@pytest.mark.asyncio
async def test_names_client_roles_and_reserved_roles_are_not_platform_role_ids(
    repo, keycloak, catalog
):
    reserved = keycloak.add_realm_role("offline_access")
    default = keycloak.add_realm_role("default-roles-agenticai")

    assert await repo.get_by_id("manager") is None
    assert await repo.get_by_id(catalog["bundle"]) is None
    assert await repo.get_by_id(reserved) is None
    assert await repo.get_by_id(default) is None
    assert await repo.get_by_id("00000000-0000-0000-0000-000000000000") is None


@pytest.mark.asyncio
async def test_token_role_names_resolve_by_name_only(repo, catalog):
    assert (await repo.get_by_name("manager")).id == catalog["manager"]
    assert await repo.get_by_name(catalog["manager"]) is None


@pytest.mark.asyncio
async def test_update_sets_bundles_by_feature_role_id_and_keeps_infrastructure_links(
    repo, keycloak, catalog
):
    updated = await repo.update(
        catalog["manager"],
        description="Line managers",
        permissions=["user:list"],
        bundle_ids=[catalog["other"]],
    )

    assert updated.description == "Line managers"
    assert updated.permissions == ("user:list",)
    assert updated.bundle_ids == (catalog["other"],)
    assert catalog["infra"] in keycloak.composites[catalog["manager"]]


@pytest.mark.asyncio
async def test_update_rejects_unknown_or_non_feature_bundle_ids(repo, catalog):
    for invalid in ("workspace", catalog["infra"], "missing"):
        with pytest.raises(BadRequestError):
            await repo.update(catalog["manager"], bundle_ids=[invalid])


@pytest.mark.asyncio
async def test_update_and_delete_of_unknown_id_report_absence(repo, keycloak, catalog):
    assert await repo.update("manager", description="x") is None
    assert await repo.delete(catalog["bundle"]) is False

    assert await repo.delete(catalog["manager"]) is True
    assert catalog["manager"] not in keycloak.roles


@pytest.mark.asyncio
async def test_create_returns_the_server_assigned_id(repo, keycloak, catalog):
    created = await repo.create(
        "auditor", description="Audit", permissions=["audit:read"], bundle_ids=[catalog["bundle"]]
    )

    assert created.id in keycloak.roles
    assert created.bundle_ids == (catalog["bundle"],)
    assert created.is_builtin is False
    assert await repo.exists("auditor") is True


@pytest.mark.asyncio
async def test_unmarked_composite_role_is_custom(repo, keycloak):
    role_id = keycloak.add_realm_role("legacy-role")
    false_id = keycloak.add_realm_role("explicit-custom", {"agentic.builtin": ["false"]})

    assert (await repo.get_by_id(role_id)).is_builtin is False
    assert (await repo.get_by_id(false_id)).is_builtin is False


@pytest.mark.asyncio
async def test_create_refuses_reserved_names(repo, catalog):
    with pytest.raises(BadRequestError):
        await repo.create("offline_access")


@pytest.mark.asyncio
async def test_list_is_sorted_and_hides_reserved_roles(repo, keycloak, catalog):
    keycloak.add_realm_role("offline_access")
    keycloak.add_realm_role("auditor")

    assert [role.name for role in await repo.get_all()] == ["auditor", "manager"]


@pytest.mark.asyncio
async def test_access_uses_expanded_keycloak_permissions_by_token_name(repo, catalog):
    assert await repo.get_access_by_names(["manager", "unknown"]) == {
        "manager": ["agent:read", "user:read"]
    }


def test_record_is_immutable():
    record = CompositeRoleRecord(
        id="1",
        name="n",
        description=None,
        permissions=(),
        bundle_ids=(),
        bundle_names=(),
        is_builtin=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.name = "other"
