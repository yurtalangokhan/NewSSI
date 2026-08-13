"""Tests for OrganizationRepository."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repository.organization_repository import OrganizationRepository


def _organization(
    *,
    organization_id: uuid.UUID | None = None,
    name: str = "Organization",
    code: str = "ORG",
    parent_id: uuid.UUID | None = None,
    path: str = "/",
    level: int = 0,
    metadata: dict[str, Any] | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=organization_id or uuid.uuid4(),
        name=name,
        code=code,
        description=None,
        parent_id=parent_id,
        path=path,
        level=level,
        order_index=0,
        is_active=True,
        metadata_json=metadata or {},
        created_at=now,
        updated_at=now,
        created_by=None,
    )


def _result(*organizations: SimpleNamespace) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(organizations)
    return result


def _count_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _row_result(rows: list[tuple[Any, Any]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _repository_with_session(session: MagicMock) -> OrganizationRepository:
    repository = OrganizationRepository()

    @asynccontextmanager
    async def session_context():
        yield session

    repository._session = session_context  # type: ignore[method-assign]
    return repository


@pytest.mark.asyncio
async def test_create_root_organization() -> None:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    org = await repository.create(
        name="Root Org",
        code="ROOT",
        parent_id=None,
        description="Test root organization",
    )

    assert org["name"] == "Root Org"
    assert org["code"] == "ROOT"
    assert org["parent_id"] is None
    assert org["path"] == "/"
    assert org["description"] == "Test root organization"


@pytest.mark.asyncio
async def test_create_child_organization_uses_parent_path() -> None:
    parent_id = uuid.uuid4()
    parent = _organization(organization_id=parent_id, path="/", level=0)
    session = MagicMock()
    session.get = AsyncMock(return_value=parent)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    child = await repository.create(name="Child Org", code="CHILD", parent_id=parent_id)

    assert child["name"] == "Child Org"
    assert child["parent_id"] == parent_id
    assert child["path"] == f"/{parent_id}/"
    assert child["level"] == 1


@pytest.mark.asyncio
async def test_create_child_organization_rejects_missing_parent() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    repository = _repository_with_session(session)
    parent_id = uuid.uuid4()

    with pytest.raises(ValueError, match=f"Parent organization {parent_id} not found"):
        await repository.create(name="Child Org", code="CHILD", parent_id=parent_id)


@pytest.mark.asyncio
async def test_get_by_id_returns_dict() -> None:
    org_id = uuid.uuid4()
    session = MagicMock()
    session.get = AsyncMock(return_value=_organization(organization_id=org_id, name="Test Org"))
    repository = _repository_with_session(session)

    org = await repository.get_by_id(org_id)

    assert org is not None
    assert org["id"] == org_id
    assert org["name"] == "Test Org"


@pytest.mark.asyncio
async def test_get_by_id_not_found() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    repository = _repository_with_session(session)

    result = await repository.get_by_id(uuid.uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_update_organization_updates_allowed_fields() -> None:
    org = _organization(name="Old Name")
    session = MagicMock()
    session.get = AsyncMock(return_value=org)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    updated = await repository.update(
        org.id,
        name="New Name",
        description="Updated description",
    )

    assert updated is not None
    assert updated["name"] == "New Name"
    assert updated["description"] == "Updated description"
    assert updated["path"] == "/"


@pytest.mark.asyncio
async def test_list_all_returns_items_and_total() -> None:
    org1 = _organization(name="Org 1", code="ORG1")
    org2 = _organization(name="Org 2", code="ORG2")
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_count_result(2), _result(org1, org2)])
    repository = _repository_with_session(session)

    orgs, total = await repository.list_all()

    assert total == 2
    assert [org["name"] for org in orgs] == ["Org 1", "Org 2"]


@pytest.mark.asyncio
async def test_get_children_adds_child_counts() -> None:
    parent_id = uuid.uuid4()
    child1 = _organization(name="Child 1", code="CHILD1", parent_id=parent_id)
    child2 = _organization(name="Child 2", code="CHILD2", parent_id=parent_id)
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _result(child1, child2),
            _row_result([(child1.id, 1)]),
        ]
    )
    repository = _repository_with_session(session)

    children = await repository.get_children(parent_id)

    assert [child["name"] for child in children] == ["Child 1", "Child 2"]
    assert children[0]["children_count"] == 1
    assert children[0]["has_children"] is True
    assert children[1]["children_count"] == 0
    assert children[1]["has_children"] is False


@pytest.mark.asyncio
async def test_get_descendants_uses_parent_path() -> None:
    root_id = uuid.uuid4()
    root = _organization(organization_id=root_id, path="/", level=0)
    dept = _organization(name="Department", code="DEPT", parent_id=root_id, path=f"/{root_id}/")
    team = _organization(name="Team", code="TEAM", parent_id=dept.id, path=f"/{root_id}/{dept.id}/")
    session = MagicMock()
    session.get = AsyncMock(return_value=root)
    session.execute = AsyncMock(side_effect=[_result(dept, team), _row_result([])])
    repository = _repository_with_session(session)

    descendants = await repository.get_children(root_id, direct_only=False)

    assert [descendant["name"] for descendant in descendants] == ["Department", "Team"]


@pytest.mark.asyncio
async def test_get_ancestors_returns_path_entries() -> None:
    root_id = uuid.uuid4()
    dept_id = uuid.uuid4()
    team_id = uuid.uuid4()
    team = _organization(organization_id=team_id, path=f"/{root_id}/{dept_id}/", level=2)
    root = _organization(organization_id=root_id, name="Root", code="ROOT")
    dept = _organization(organization_id=dept_id, name="Department", code="DEPT")
    session = MagicMock()
    session.get = AsyncMock(return_value=team)
    session.execute = AsyncMock(return_value=_result(root, dept))
    repository = _repository_with_session(session)

    ancestors = await repository.get_ancestors(team_id)

    assert [ancestor["name"] for ancestor in ancestors] == ["Root", "Department"]


@pytest.mark.asyncio
async def test_move_organization_updates_descendant_paths() -> None:
    root1_id = uuid.uuid4()
    root2_id = uuid.uuid4()
    child_id = uuid.uuid4()
    grandchild_id = uuid.uuid4()
    root2 = _organization(organization_id=root2_id, path="/", level=0)
    child = _organization(
        organization_id=child_id,
        parent_id=root1_id,
        path=f"/{root1_id}/",
        level=1,
    )
    grandchild = _organization(
        organization_id=grandchild_id,
        parent_id=child_id,
        path=f"/{root1_id}/{child_id}/",
        level=2,
    )
    session = MagicMock()
    session.get = AsyncMock(side_effect=[child, root2])
    session.execute = AsyncMock(return_value=_result(grandchild))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    moved = await repository.move_organization(child_id, root2_id)

    assert moved is not None
    assert moved["parent_id"] == root2_id
    assert moved["path"] == f"/{root2_id}/"
    assert grandchild.path == f"/{root2_id}/{child_id}/"


@pytest.mark.asyncio
async def test_get_tree_builds_hierarchy() -> None:
    root = _organization(name="Root", code="ROOT")
    child1 = _organization(name="Child 1", code="CHILD1", parent_id=root.id, path=f"/{root.id}/", level=1)
    child2 = _organization(name="Child 2", code="CHILD2", parent_id=root.id, path=f"/{root.id}/", level=1)
    grandchild = _organization(
        name="Grandchild",
        code="GRANDCHILD",
        parent_id=child1.id,
        path=f"/{root.id}/{child1.id}/",
        level=2,
    )
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _result(root, child1, child2, grandchild),
            _row_result([(root.id, 2), (child1.id, 1)]),
        ]
    )
    repository = _repository_with_session(session)

    tree = await repository.get_tree()

    roots = tree["roots"]
    assert len(roots) == 1
    assert roots[0]["name"] == "Root"
    assert len(roots[0]["children"]) == 2
    child1_node = next(child for child in roots[0]["children"] if child["name"] == "Child 1")
    assert child1_node["children"][0]["name"] == "Grandchild"


@pytest.mark.asyncio
async def test_metadata_storage() -> None:
    metadata = {"region": "US-West", "cost_center": "12345", "tags": ["prod"]}
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    repository = _repository_with_session(session)

    org = await repository.create(
        name="Org with Metadata",
        code="METADATA",
        parent_id=None,
        metadata=metadata,
    )

    assert org["metadata"]["region"] == "US-West"
    assert org["metadata"]["cost_center"] == "12345"
    assert "prod" in org["metadata"]["tags"]
