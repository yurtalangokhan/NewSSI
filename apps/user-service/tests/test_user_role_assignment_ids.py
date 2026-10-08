"""User role assignment endpoints take Keycloak realm-role IDs, never names."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import BadRequestError, NotFoundError
import pytest

from tests.error_support import raises_localized
from src.repository.keycloak_role_client import catalog_cache
from src.schema.users import UserRoleRequest, UserUpdateRequest
from src.service.user_service import UserService
from tests.fakes.keycloak_roles import FakeKeycloakRoles


class Assignments:
    """Records assignment writes the way the Keycloak role-mapping repository applies them."""

    def __init__(self, ids, current):
        self.ids = ids
        self.current = list(current)
        self.assign_roles = AsyncMock(side_effect=self._assign)
        self.replace_roles = AsyncMock(side_effect=self._replace)
        self.remove_role = AsyncMock(side_effect=self._remove)
        self.set_primary_role = AsyncMock(side_effect=self._primary)

    async def list_user_roles(self, user_id):
        primary = self.current[0] if self.current else None
        return [
            {"id": self.ids[name], "name": name, "is_primary": name == primary}
            for name in self.current
        ]

    async def _assign(self, user_id, names, primary_role=None):
        # Assigning adds grants; it never drops the user's existing roles.
        merged = [*self.current, *[n for n in names if n not in self.current]]
        if primary_role:
            merged = [primary_role, *[n for n in merged if n != primary_role]]
        self.current = merged

    async def _replace(self, user_id, names, primary_role=None):
        self.current = list(names)
        return 1

    async def _remove(self, user_id, name):
        if name not in self.current:
            return False
        self.current.remove(name)
        return True

    async def _primary(self, user_id, name):
        if name not in self.current:
            return False
        self.current = [name, *[n for n in self.current if n != name]]
        return True


@pytest.fixture
def setup():
    catalog_cache.clear()
    keycloak = FakeKeycloakRoles()
    ids = {name: keycloak.add_realm_role(name) for name in ("enduser", "auditor", "operator")}
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, keycloak_id=str(user_id), role="enduser", email="u@x")
    service = UserService()
    service.role_repo.client = keycloak
    service.user_role_repo = Assignments(ids, ["enduser"])
    service.user_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    service.permission_resolver = SimpleNamespace(invalidate_user=AsyncMock())
    service.keycloak = SimpleNamespace(
        logout_user_sessions=AsyncMock(return_value=True),
        get_user_by_email=AsyncMock(return_value=None),
        create_user=AsyncMock(side_effect=lambda payload: str(uuid.uuid4())),
    )
    service._user_to_dict = lambda user: {"id": str(user.id)}
    yield service, ids, user_id
    catalog_cache.clear()


@pytest.mark.asyncio
async def test_assign_roles_resolves_keycloak_ids_to_role_mappings(setup):
    service, ids, user_id = setup

    result = await service.assign_roles(
        user_id, [ids["auditor"], ids["operator"]], primary_role_id=ids["operator"]
    )

    service.user_role_repo.assign_roles.assert_awaited_once_with(
        user_id, ["auditor", "operator"], primary_role="operator"
    )
    assert result["roles"][0] == {"id": ids["operator"], "name": "operator", "is_primary": True}


@pytest.mark.asyncio
async def test_assign_roles_rejects_names_and_an_unassigned_primary(setup):
    service, ids, user_id = setup

    with raises_localized(BadRequestError, "auditor"):
        await service.assign_roles(user_id, ["auditor"])
    with pytest.raises(BadRequestError):
        await service.assign_roles(user_id, [ids["auditor"]], primary_role_id=ids["operator"])
    service.user_role_repo.assign_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_and_primary_address_the_assignment_by_role_id(setup):
    service, ids, user_id = setup
    await service.assign_roles(user_id, [ids["auditor"]])

    await service.set_primary_role(user_id, ids["auditor"])
    assert service.user_role_repo.current[0] == "auditor"
    with pytest.raises(NotFoundError):
        await service.set_primary_role(user_id, "enduser")

    with pytest.raises(NotFoundError):
        await service.remove_role(user_id, "enduser")
    await service.remove_role(user_id, ids["enduser"])
    assert service.user_role_repo.current == ["auditor"]


@pytest.mark.asyncio
async def test_replace_role_takes_a_role_id(setup):
    service, ids, user_id = setup

    await service.replace_role(user_id, ids["auditor"])

    service.user_role_repo.replace_roles.assert_awaited_once_with(
        user_id, ["auditor"], primary_role="auditor"
    )
    with pytest.raises(BadRequestError):
        await service.replace_role(user_id, "auditor")


@pytest.mark.asyncio
async def test_internal_membership_role_changes_resolve_names_strictly(setup):
    service, ids, user_id = setup

    await service.set_user_role(user_id, "operator")
    assert service.user_role_repo.current == ["operator"]
    with pytest.raises(BadRequestError):
        await service.set_user_role(user_id, ids["auditor"])


def test_role_change_contracts_carry_a_role_id_only():
    assert UserRoleRequest(role_id="kc-id").role_id == "kc-id"
    assert "role" not in UserRoleRequest.model_fields
    assert "role" not in UserUpdateRequest.model_fields


def _creatable(service, user_id):
    created = SimpleNamespace(id=user_id, keycloak_id=None, role=None)

    async def create(**fields):
        created.role = fields["role"]
        return created

    service.user_repo = SimpleNamespace(
        exists_by_email=AsyncMock(return_value=False),
        create=AsyncMock(side_effect=create),
        get_by_id=AsyncMock(return_value=created),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())
    service._user_to_dict = lambda user: {"role": user.role}


@pytest.mark.asyncio
async def test_create_user_takes_an_initial_role_id_and_defaults_to_enduser(setup):
    service, ids, user_id = setup
    _creatable(service, user_id)

    assert await service.create_user("a@x.test", role_id=ids["auditor"]) == {"role": "auditor"}
    assert await service.create_user("b@x.test") == {"role": "enduser"}
    with pytest.raises(BadRequestError):
        await service.create_user("c@x.test", role_id="auditor")


def test_create_contract_carries_a_role_id():
    from src.schema.users import UserCreateRequest

    assert "role" not in UserCreateRequest.model_fields
    assert UserCreateRequest.model_fields["role_id"].default is None


@pytest.mark.asyncio
async def test_invited_users_start_with_the_default_role(setup):
    service, _, user_id = setup
    _creatable(service, user_id)

    assert await service.invite_users(["new@x.test"]) == [{"role": "enduser"}]
