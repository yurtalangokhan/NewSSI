"""Regression tests for organization hierarchy moves."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repository.organization_repository import OrganizationRepository


def _organization(
    organization_id: uuid.UUID,
    *,
    parent_id: uuid.UUID | None,
    path: str,
    level: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=organization_id,
        parent_id=parent_id,
        path=path,
        level=level,
    )


def _repository_with_session(session: MagicMock) -> OrganizationRepository:
    repository = OrganizationRepository()

    @asynccontextmanager
    async def session_context():
        yield session

    repository._session = session_context  # type: ignore[method-assign]
    repository._to_dict = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda organization: {
            "id": organization.id,
            "parent_id": organization.parent_id,
            "path": organization.path,
            "level": organization.level,
        }
    )
    return repository


@pytest.mark.asyncio
async def test_move_organization_allows_moving_descendant_to_ancestor() -> None:
    root_id = uuid.uuid4()
    current_parent_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    root = _organization(root_id, parent_id=None, path="/", level=0)
    organization = _organization(
        organization_id,
        parent_id=current_parent_id,
        path=f"/{root_id}/{current_parent_id}/",
        level=2,
    )
    session = MagicMock()
    session.get = AsyncMock(side_effect=[organization, root])
    descendants_result = MagicMock()
    descendants_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=descendants_result)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    moved = await repository.move_organization(organization_id, root_id)

    assert moved == {
        "id": organization_id,
        "parent_id": root_id,
        "path": f"/{root_id}/",
        "level": 1,
    }


@pytest.mark.asyncio
async def test_move_organization_rejects_moving_to_descendant() -> None:
    root_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    descendant_id = uuid.uuid4()
    organization = _organization(
        organization_id,
        parent_id=root_id,
        path=f"/{root_id}/",
        level=1,
    )
    descendant = _organization(
        descendant_id,
        parent_id=organization_id,
        path=f"/{root_id}/{organization_id}/",
        level=2,
    )
    session = MagicMock()
    session.get = AsyncMock(side_effect=[organization, descendant])
    repository = _repository_with_session(session)

    with pytest.raises(ValueError, match="Cannot move organization to its own descendant"):
        await repository.move_organization(organization_id, descendant_id)
