"""Platform role grant changes revoke the sessions of the users who hold the role."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import ConflictError
import pytest

from src.repository.keycloak_role_client import catalog_cache
from src.service.role_service import CompositeRoleService
from tests.error_support import raises_localized
from tests.fakes.keycloak_roles import FakeKeycloakRoles


@pytest.fixture
def setup():
    catalog_cache.clear()
    keycloak = FakeKeycloakRoles()
    role_id = keycloak.add_realm_role("analyst", {"agentic.permissions": ["document:read"]})
    holder = uuid.uuid4()
    service = CompositeRoleService()
    service.role_repo.client = keycloak
    service.permission_repo = SimpleNamespace(
        get_all=AsyncMock(return_value=[SimpleNamespace(name="document:list")])
    )
    service.user_role_repo = SimpleNamespace(list_user_ids_by_role=AsyncMock(return_value=[holder]))
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True, logout_user_sessions=AsyncMock(return_value=True)
    )
    yield service, keycloak, role_id, holder
    catalog_cache.clear()


@pytest.mark.asyncio
async def test_set_role_permissions_by_id_invalidates_sessions_for_assigned_users(setup):
    service, keycloak, role_id, holder = setup

    result = await service.set_role_permissions(role_id, ["document:list"])

    assert result["permissions"] == ["document:list"]
    assert keycloak.roles[role_id]["attributes"]["agentic.permissions"] == ["document:list"]
    service.user_role_repo.list_user_ids_by_role.assert_awaited_once_with("analyst")
    service.keycloak.logout_user_sessions.assert_awaited_once_with(str(holder))


@pytest.mark.asyncio
async def test_delete_role_rejects_assigned_roles(setup):
    service, keycloak, role_id, _ = setup

    with raises_localized(ConflictError, "users are assigned"):
        await service.delete_role(role_id)
    assert role_id in keycloak.roles
