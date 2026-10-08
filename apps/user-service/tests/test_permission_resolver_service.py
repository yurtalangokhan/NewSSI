"""Effective access is expanded from Keycloak role composites, never from local data."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.repository.keycloak_role_client import catalog_cache
from src.service.permission_resolver_service import PermissionResolverService
from tests.fakes.keycloak_roles import FakeKeycloakRoles


@pytest.fixture
def keycloak():
    catalog_cache.clear()
    fake = FakeKeycloakRoles()
    agent = fake.add_client("agent-service")
    workspace = fake.add_client_role(
        agent, "workspace", {"agentic.permissions": ["agent:read", "thread:read"]}
    )
    auditor = fake.add_realm_role("auditor", {"agentic.permissions": ["user:list"]})
    operator = fake.add_realm_role("operator", {"agentic.permissions": ["project:read"]})
    fake.add_realm_role("system-admin")
    fake.link(operator, workspace)
    fake.ids = {"auditor": auditor, "operator": operator}
    yield fake
    catalog_cache.clear()


def _resolver(keycloak, role_names, client_permissions=()):
    resolver = PermissionResolverService(cache_ttl_seconds=0)
    resolver.role_repo.client = keycloak
    resolver.user_repo = SimpleNamespace(get_by_id=AsyncMock())
    resolver.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(return_value=[{"name": name} for name in role_names]),
        effective_client_permissions=AsyncMock(return_value=list(client_permissions)),
    )
    return resolver


@pytest.mark.asyncio
async def test_permissions_union_direct_and_bundled_grants_across_roles(keycloak):
    resolver = _resolver(keycloak, ["auditor", "operator"])

    assert await resolver.resolve_effective_access(uuid.uuid4()) == (
        ["agent:read", "project:read", "thread:read", "user:list"],
        False,
    )


@pytest.mark.asyncio
async def test_direct_client_role_grants_apply_without_realm_roles(keycloak):
    resolver = _resolver(keycloak, [], client_permissions=["tool:read"])

    assert await resolver.resolve_effective_access(uuid.uuid4()) == (["tool:read"], False)


@pytest.mark.asyncio
async def test_no_assignment_grants_nothing_and_never_reads_the_user(keycloak):
    resolver = _resolver(keycloak, [])

    assert await resolver.resolve_effective_access(uuid.uuid4()) == ([], False)
    resolver.user_repo.get_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_system_admin_holds_the_wildcard_and_the_admin_flag(keycloak):
    resolver = _resolver(keycloak, ["system-admin", "auditor"])

    assert await resolver.resolve_effective_access(uuid.uuid4()) == (["*"], True)


@pytest.mark.asyncio
async def test_unknown_token_roles_are_ignored(keycloak):
    resolver = _resolver(keycloak, ["ghost", "auditor"])

    assert await resolver.resolve_effective_permissions(uuid.uuid4()) == ["user:list"]
