"""
Tests for ResourcePermissionService.

Tests permission checking logic with 3-tier priority:
1. Direct user permissions
2. Organization permissions
3. Inherited organization permissions
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.service.resource_permission_service import ResourcePermissionService


@pytest.fixture
def mock_repo():
    """Mock repository for testing."""
    repo = MagicMock()
    repo.grant_permission = AsyncMock()
    repo.revoke_permission = AsyncMock()
    repo.get_user_permissions = AsyncMock(return_value=[])
    repo.get_organization_permissions = AsyncMock(return_value=[])
    repo.list_by_resource = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_org_repo():
    """Mock organization repository."""
    repo = MagicMock()
    repo.get_ancestors = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_user_org_repo():
    """Mock user-organization repository."""
    repo = MagicMock()
    repo.get_user_organizations = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def service(mock_repo, mock_org_repo, mock_user_org_repo):
    """ResourcePermissionService with mocked dependencies."""
    return ResourcePermissionService(
        permission_repo=mock_repo,
        organization_repo=mock_org_repo,
        user_org_repo=mock_user_org_repo,
    )


@pytest.mark.asyncio
class TestResourcePermissionService:
    """Test suite for ResourcePermissionService."""

    async def test_grant_user_permission(self, service, mock_repo):
        """Test granting direct user permission."""
        user_id = uuid.uuid4()
        resource_id = "agent-123"
        granted_by = uuid.uuid4()

        mock_repo.grant_permission.return_value = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "resource_type": "agent",
            "resource_id": resource_id,
            "permission_level": "read",
            "granted_by": granted_by,
        }

        result = await service.grant_permission(
            user_id=user_id,
            resource_type="agent",
            resource_id=resource_id,
            permission_level="read",
            granted_by=granted_by,
        )

        assert result is not None
        assert result["user_id"] == user_id
        assert result["resource_id"] == resource_id
        mock_repo.grant_permission.assert_called_once()

    async def test_grant_organization_permission(self, service, mock_repo):
        """Test granting organization-level permission."""
        org_id = uuid.uuid4()
        resource_id = "collection-456"
        granted_by = uuid.uuid4()

        mock_repo.grant_permission.return_value = {
            "id": uuid.uuid4(),
            "organization_id": org_id,
            "resource_type": "rag_collection",
            "resource_id": resource_id,
            "permission_level": "write",
            "granted_by": granted_by,
        }

        result = await service.grant_permission(
            organization_id=org_id,
            resource_type="rag_collection",
            resource_id=resource_id,
            permission_level="write",
            granted_by=granted_by,
        )

        assert result is not None
        assert result["organization_id"] == org_id
        mock_repo.grant_permission.assert_called_once()

    async def test_revoke_permission(self, service, mock_repo):
        """Test revoking a permission."""
        permission_id = uuid.uuid4()
        mock_repo.revoke_permission.return_value = True

        result = await service.revoke_permission(permission_id)

        assert result is True
        mock_repo.revoke_permission.assert_called_once_with(permission_id)

    async def test_check_permission_direct_user(self, service, mock_repo, mock_user_org_repo):
        """Test permission check with direct user permission (highest priority)."""
        user_id = uuid.uuid4()
        resource_id = "agent-123"

        # User has direct "write" permission
        mock_repo.get_user_permissions.return_value = [
            {
                "permission_level": "write",
                "resource_type": "agent",
                "resource_id": resource_id,
            }
        ]

        # User is also in organization with "read" (should be ignored)
        org_id = uuid.uuid4()
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_organization_permissions.return_value = [
            {
                "permission_level": "read",
                "resource_type": "agent",
                "resource_id": resource_id,
            }
        ]

        result = await service.check_permission(
            user_id=user_id,
            resource_type="agent",
            resource_id=resource_id,
            required_permission="read",
        )

        assert result["allowed"] is True
        assert result["permission_level"] == "write"
        assert result["source"] == "user"

    async def test_check_permission_organization(self, service, mock_repo, mock_user_org_repo):
        """Test permission check via organization membership."""
        user_id = uuid.uuid4()
        resource_id = "collection-456"
        org_id = uuid.uuid4()

        # No direct user permission
        mock_repo.get_user_permissions.return_value = []

        # User is in organization with permission
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_organization_permissions.return_value = [
            {
                "permission_level": "read",
                "resource_type": "rag_collection",
                "resource_id": resource_id,
                "organization_id": org_id,
            }
        ]

        result = await service.check_permission(
            user_id=user_id,
            resource_type="rag_collection",
            resource_id=resource_id,
            required_permission="read",
        )

        assert result["allowed"] is True
        assert result["permission_level"] == "read"
        assert result["source"] == "organization"

    async def test_check_permission_inherited(
        self, service, mock_repo, mock_user_org_repo, mock_org_repo
    ):
        """Test permission check via inherited organization permission."""
        user_id = uuid.uuid4()
        resource_id = "agent-789"
        child_org_id = uuid.uuid4()
        parent_org_id = uuid.uuid4()

        # No direct user permission
        mock_repo.get_user_permissions.return_value = []

        # User is in child organization
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": child_org_id}]

        # No permission on child organization
        mock_repo.get_organization_permissions.return_value = []

        # Parent organization has permission
        mock_org_repo.get_ancestors.return_value = [{"id": parent_org_id, "name": "Parent Org"}]

        # Mock ancestor permission lookup
        async def get_org_perms(org_ids, resource_type, resource_id):
            if parent_org_id in org_ids:
                return [
                    {
                        "permission_level": "execute",
                        "resource_type": "agent",
                        "resource_id": resource_id,
                        "organization_id": parent_org_id,
                    }
                ]
            return []

        mock_repo.get_organization_permissions.side_effect = get_org_perms

        result = await service.check_permission(
            user_id=user_id,
            resource_type="agent",
            resource_id=resource_id,
            required_permission="execute",
        )

        assert result["allowed"] is True
        assert result["permission_level"] == "execute"
        assert result["source"] == "inherited"

    async def test_check_permission_insufficient_level(
        self, service, mock_repo, mock_user_org_repo
    ):
        """Test permission denied when level is insufficient."""
        user_id = uuid.uuid4()
        resource_id = "collection-999"

        # User has "read" but needs "write"
        mock_repo.get_user_permissions.return_value = [
            {
                "permission_level": "read",
                "resource_type": "rag_collection",
                "resource_id": resource_id,
            }
        ]
        mock_user_org_repo.get_user_organizations.return_value = []

        result = await service.check_permission(
            user_id=user_id,
            resource_type="rag_collection",
            resource_id=resource_id,
            required_permission="write",
        )

        assert result["allowed"] is False
        assert result["permission_level"] is None

    async def test_check_permission_no_access(self, service, mock_repo, mock_user_org_repo):
        """Test permission denied when user has no access."""
        user_id = uuid.uuid4()
        resource_id = "connector-404"

        mock_repo.get_user_permissions.return_value = []
        mock_user_org_repo.get_user_organizations.return_value = []

        result = await service.check_permission(
            user_id=user_id,
            resource_type="connector",
            resource_id=resource_id,
            required_permission="read",
        )

        assert result["allowed"] is False
        assert result["permission_level"] is None
        assert result["source"] is None

    async def test_permission_level_hierarchy(self, service):
        """Test permission level comparison logic."""
        # owner > admin > write > read > execute
        assert service._has_sufficient_permission("owner", "read") is True
        assert service._has_sufficient_permission("admin", "write") is True
        assert service._has_sufficient_permission("write", "read") is True
        assert service._has_sufficient_permission("read", "execute") is True

        assert service._has_sufficient_permission("read", "write") is False
        assert service._has_sufficient_permission("execute", "admin") is False

    async def test_get_user_accessible_resources(
        self, service, mock_repo, mock_user_org_repo, mock_org_repo
    ):
        """Test listing all resources a user can access."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        # Direct permissions
        mock_repo.get_user_permissions.return_value = [
            {"resource_id": "agent-1", "permission_level": "read"},
            {"resource_id": "agent-2", "permission_level": "write"},
        ]

        # Organization permissions
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_organization_permissions.return_value = [
            {"resource_id": "agent-3", "permission_level": "execute"},
        ]
        mock_org_repo.get_ancestors.return_value = []

        result = await service.get_user_accessible_resources(user_id=user_id, resource_type="agent")

        assert len(result["resources"]) == 3
        resource_ids = [r["resource_id"] for r in result["resources"]]
        assert "agent-1" in resource_ids
        assert "agent-2" in resource_ids
        assert "agent-3" in resource_ids

    async def test_list_resource_permissions(self, service, mock_repo):
        """Test listing all permissions for a resource."""
        resource_id = "agent-777"

        mock_repo.list_by_resource.return_value = [
            {
                "id": uuid.uuid4(),
                "user_id": uuid.uuid4(),
                "permission_level": "owner",
            },
            {
                "id": uuid.uuid4(),
                "organization_id": uuid.uuid4(),
                "permission_level": "read",
            },
        ]

        result = await service.list_resource_permissions(
            resource_type="agent", resource_id=resource_id
        )

        assert len(result) == 2
        assert any(p["permission_level"] == "owner" for p in result)
        assert any(p["permission_level"] == "read" for p in result)

    async def test_bulk_check_permissions(self, service, mock_repo, mock_user_org_repo):
        """Test bulk permission checking for multiple resources."""
        user_id = uuid.uuid4()

        mock_repo.get_user_permissions.return_value = [
            {"resource_id": "agent-1", "permission_level": "read"},
            {"resource_id": "agent-2", "permission_level": "write"},
        ]
        mock_user_org_repo.get_user_organizations.return_value = []

        resource_ids = ["agent-1", "agent-2", "agent-3"]
        result = await service.bulk_check_permissions(
            user_id=user_id,
            resource_type="agent",
            resource_ids=resource_ids,
            required_permission="read",
        )

        assert result["agent-1"]["allowed"] is True
        assert result["agent-2"]["allowed"] is True
        assert result["agent-3"]["allowed"] is False
