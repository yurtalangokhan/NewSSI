"""Hierarchy move contracts remain stable when Keycloak owns parent links."""

from uuid import UUID

from error_contract import BadRequestError
import pytest

from src.repository.organization_repository import OrganizationRepository
from tests.test_keycloak_organizations import CHILD, ROOT, Admin

GRANDCHILD = UUID(int=4)
DESTINATION = UUID(int=5)


@pytest.mark.asyncio
async def test_move_preserves_descendant_ids_and_recomputes_paths():
    admin = Admin()
    admin.groups[str(GRANDCHILD)] = {
        "id": str(GRANDCHILD),
        "name": "Grandchild",
        "parentId": str(CHILD),
    }
    admin.groups[str(DESTINATION)] = {
        "id": str(DESTINATION),
        "name": "Destination",
        "parentId": str(ROOT),
    }
    repo = OrganizationRepository(admin)
    moved = await repo.move_organization(CHILD, DESTINATION)
    assert moved["parent_id"] == DESTINATION
    assert moved["path"] == f"/{ROOT}/{DESTINATION}/"
    descendant = await repo.get_by_id(GRANDCHILD)
    assert descendant["path"] == f"/{ROOT}/{DESTINATION}/{CHILD}/"
    assert descendant["level"] == 3
    promoted = await repo.move_organization(GRANDCHILD, ROOT)
    assert promoted["level"] == 1
    assert promoted["path"] == f"/{ROOT}/"


@pytest.mark.asyncio
async def test_move_rejects_self_and_descendants():
    repo = OrganizationRepository(Admin())
    for target in (ROOT, CHILD):
        with pytest.raises(BadRequestError):
            await repo.move_organization(ROOT, target)
