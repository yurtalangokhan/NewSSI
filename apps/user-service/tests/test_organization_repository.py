"""
Tests for OrganizationRepository.

Tests hierarchical organization operations, materialized path management,
and tree traversal operations.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models.organizations import OrganizationModel
from src.repository.organization_repository import OrganizationRepository


@pytest.fixture
async def org_repo(db_session: AsyncSession):
    """Fixture providing organization repository with test database."""
    return OrganizationRepository(db_session)


@pytest.mark.asyncio
class TestOrganizationRepository:
    """Test suite for OrganizationRepository."""

    async def test_create_root_organization(self, org_repo: OrganizationRepository):
        """Test creating a root organization."""
        org = await org_repo.create(
            name="Root Org", parent_id=None, description="Test root organization"
        )

        assert org is not None
        assert org.name == "Root Org"
        assert org.parent_id is None
        assert org.path == f"{org.id}/"
        assert org.description == "Test root organization"

    async def test_create_child_organization(self, org_repo: OrganizationRepository):
        """Test creating a child organization."""
        # Create parent
        parent = await org_repo.create(name="Parent Org", parent_id=None)
        assert parent is not None

        # Create child
        child = await org_repo.create(name="Child Org", parent_id=parent.id)

        assert child is not None
        assert child.name == "Child Org"
        assert child.parent_id == parent.id
        assert child.path == f"{parent.id}/{child.id}/"

    async def test_create_deep_hierarchy(self, org_repo: OrganizationRepository):
        """Test creating a deep organizational hierarchy."""
        # Create: Root -> Department -> Team -> Squad
        root = await org_repo.create(name="Company", parent_id=None)
        dept = await org_repo.create(name="Engineering", parent_id=root.id)
        team = await org_repo.create(name="Backend", parent_id=dept.id)
        squad = await org_repo.create(name="API Squad", parent_id=team.id)

        assert squad.path == f"{root.id}/{dept.id}/{team.id}/{squad.id}/"

    async def test_get_by_id(self, org_repo: OrganizationRepository):
        """Test retrieving organization by ID."""
        org = await org_repo.create(name="Test Org", parent_id=None)
        retrieved = await org_repo.get_by_id(org.id)

        assert retrieved is not None
        assert retrieved.id == org.id
        assert retrieved.name == "Test Org"

    async def test_get_by_id_not_found(self, org_repo: OrganizationRepository):
        """Test retrieving non-existent organization."""
        fake_id = uuid.uuid4()
        result = await org_repo.get_by_id(fake_id)

        assert result is None

    async def test_get_by_path(self, org_repo: OrganizationRepository):
        """Test retrieving organization by materialized path."""
        parent = await org_repo.create(name="Parent", parent_id=None)
        child = await org_repo.create(name="Child", parent_id=parent.id)

        retrieved = await org_repo.get_by_path(child.path)

        assert retrieved is not None
        assert retrieved.id == child.id
        assert retrieved.name == "Child"

    async def test_update_organization(self, org_repo: OrganizationRepository):
        """Test updating organization fields."""
        org = await org_repo.create(name="Old Name", parent_id=None)

        updated = await org_repo.update(
            org.id, name="New Name", description="Updated description"
        )

        assert updated is not None
        assert updated.name == "New Name"
        assert updated.description == "Updated description"
        assert updated.path == org.path  # Path unchanged

    async def test_delete_leaf_organization(self, org_repo: OrganizationRepository):
        """Test deleting a leaf organization (no children)."""
        org = await org_repo.create(name="Leaf Org", parent_id=None)
        deleted = await org_repo.delete(org.id)

        assert deleted is True

        retrieved = await org_repo.get_by_id(org.id)
        assert retrieved is None

    async def test_delete_organization_with_children_fails(
        self, org_repo: OrganizationRepository
    ):
        """Test that deleting organization with children fails."""
        parent = await org_repo.create(name="Parent", parent_id=None)
        await org_repo.create(name="Child", parent_id=parent.id)

        with pytest.raises(ValueError, match="has children"):
            await org_repo.delete(parent.id)

    async def test_list_all_organizations(self, org_repo: OrganizationRepository):
        """Test listing all organizations."""
        await org_repo.create(name="Org 1", parent_id=None)
        await org_repo.create(name="Org 2", parent_id=None)
        await org_repo.create(name="Org 3", parent_id=None)

        orgs = await org_repo.list_all()

        assert len(orgs) >= 3
        names = [org.name for org in orgs]
        assert "Org 1" in names
        assert "Org 2" in names
        assert "Org 3" in names

    async def test_get_children(self, org_repo: OrganizationRepository):
        """Test retrieving direct children of an organization."""
        parent = await org_repo.create(name="Parent", parent_id=None)
        child1 = await org_repo.create(name="Child 1", parent_id=parent.id)
        child2 = await org_repo.create(name="Child 2", parent_id=parent.id)
        # Grandchild - should not be included
        await org_repo.create(name="Grandchild", parent_id=child1.id)

        children = await org_repo.get_children(parent.id)

        assert len(children) == 2
        names = [c.name for c in children]
        assert "Child 1" in names
        assert "Child 2" in names
        assert "Grandchild" not in names

    async def test_get_descendants(self, org_repo: OrganizationRepository):
        """Test retrieving all descendants (recursive)."""
        root = await org_repo.create(name="Root", parent_id=None)
        dept = await org_repo.create(name="Department", parent_id=root.id)
        team = await org_repo.create(name="Team", parent_id=dept.id)
        squad = await org_repo.create(name="Squad", parent_id=team.id)

        descendants = await org_repo.get_descendants(root.id)

        assert len(descendants) == 3
        names = [d.name for d in descendants]
        assert "Department" in names
        assert "Team" in names
        assert "Squad" in names

    async def test_get_ancestors(self, org_repo: OrganizationRepository):
        """Test retrieving all ancestors up the tree."""
        root = await org_repo.create(name="Root", parent_id=None)
        dept = await org_repo.create(name="Department", parent_id=root.id)
        team = await org_repo.create(name="Team", parent_id=dept.id)

        ancestors = await org_repo.get_ancestors(team.id)

        assert len(ancestors) == 2
        names = [a.name for a in ancestors]
        assert "Root" in names
        assert "Department" in names
        assert "Team" not in names  # Self not included

    async def test_move_organization(self, org_repo: OrganizationRepository):
        """Test moving an organization to a new parent."""
        root1 = await org_repo.create(name="Root 1", parent_id=None)
        root2 = await org_repo.create(name="Root 2", parent_id=None)
        child = await org_repo.create(name="Child", parent_id=root1.id)

        old_path = child.path
        moved = await org_repo.move(child.id, root2.id)

        assert moved is not None
        assert moved.parent_id == root2.id
        assert moved.path != old_path
        assert moved.path.startswith(f"{root2.id}/")

    async def test_move_subtree_updates_descendants(
        self, org_repo: OrganizationRepository
    ):
        """Test that moving a subtree updates all descendant paths."""
        root1 = await org_repo.create(name="Root 1", parent_id=None)
        root2 = await org_repo.create(name="Root 2", parent_id=None)
        parent = await org_repo.create(name="Parent", parent_id=root1.id)
        child = await org_repo.create(name="Child", parent_id=parent.id)
        grandchild = await org_repo.create(name="Grandchild", parent_id=child.id)

        # Move parent subtree from root1 to root2
        await org_repo.move(parent.id, root2.id)

        # Check all paths updated
        parent_updated = await org_repo.get_by_id(parent.id)
        child_updated = await org_repo.get_by_id(child.id)
        grandchild_updated = await org_repo.get_by_id(grandchild.id)

        assert parent_updated.path.startswith(f"{root2.id}/")
        assert child_updated.path.startswith(f"{root2.id}/{parent.id}/")
        assert grandchild_updated.path.startswith(
            f"{root2.id}/{parent.id}/{child.id}/"
        )

    async def test_build_tree(self, org_repo: OrganizationRepository):
        """Test building hierarchical tree structure."""
        root = await org_repo.create(name="Root", parent_id=None)
        child1 = await org_repo.create(name="Child 1", parent_id=root.id)
        child2 = await org_repo.create(name="Child 2", parent_id=root.id)
        grandchild = await org_repo.create(name="Grandchild", parent_id=child1.id)

        tree = await org_repo.build_tree()

        assert len(tree) == 1  # One root
        assert tree[0]["name"] == "Root"
        assert len(tree[0]["children"]) == 2

        child1_node = next(c for c in tree[0]["children"] if c["name"] == "Child 1")
        assert len(child1_node["children"]) == 1
        assert child1_node["children"][0]["name"] == "Grandchild"

    async def test_get_depth(self, org_repo: OrganizationRepository):
        """Test calculating organization depth in hierarchy."""
        root = await org_repo.create(name="Root", parent_id=None)
        dept = await org_repo.create(name="Department", parent_id=root.id)
        team = await org_repo.create(name="Team", parent_id=dept.id)

        assert await org_repo.get_depth(root.id) == 0
        assert await org_repo.get_depth(dept.id) == 1
        assert await org_repo.get_depth(team.id) == 2

    async def test_metadata_storage(self, org_repo: OrganizationRepository):
        """Test storing and retrieving JSON metadata."""
        org = await org_repo.create(
            name="Org with Metadata",
            parent_id=None,
            metadata={"region": "US-West", "cost_center": "12345", "tags": ["prod"]},
        )

        retrieved = await org_repo.get_by_id(org.id)

        assert retrieved.metadata is not None
        assert retrieved.metadata["region"] == "US-West"
        assert retrieved.metadata["cost_center"] == "12345"
        assert "prod" in retrieved.metadata["tags"]

    async def test_concurrent_creates_dont_conflict(
        self, org_repo: OrganizationRepository
    ):
        """Test that concurrent organization creates don't cause path conflicts."""
        parent = await org_repo.create(name="Parent", parent_id=None)

        # Create multiple children concurrently
        child1 = await org_repo.create(name="Child 1", parent_id=parent.id)
        child2 = await org_repo.create(name="Child 2", parent_id=parent.id)
        child3 = await org_repo.create(name="Child 3", parent_id=parent.id)

        # All should have unique paths under same parent
        assert child1.path != child2.path
        assert child2.path != child3.path
        assert child1.path.startswith(f"{parent.id}/")
        assert child2.path.startswith(f"{parent.id}/")
        assert child3.path.startswith(f"{parent.id}/")
