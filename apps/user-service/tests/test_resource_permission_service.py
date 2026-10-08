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
    repo.create = AsyncMock()
    repo.delete = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_org_resource = AsyncMock(return_value=None)
    repo.get_by_user_resource = AsyncMock(return_value=None)
    repo.get_resource_permissions = AsyncMock(return_value=[])
    repo.get_user_permissions = AsyncMock(return_value=[])
    repo.get_organization_permissions = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_org_repo():
    """Mock organization repository."""
    repo = MagicMock()
    repo.get_ancestors = AsyncMock(return_value=[])
    repo.get_by_id = AsyncMock(return_value={"name": "Organization"})
    return repo


@pytest.fixture
def mock_user_org_repo():
    """Mock user-organization repository."""
    repo = MagicMock()
    repo.get_user_organizations = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_audit_repo():
    """Mock permission audit repository."""
    repo = MagicMock()
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo, mock_org_repo, mock_user_org_repo, mock_audit_repo):
    """ResourcePermissionService with mocked dependencies."""

    async def project_mutation(mutation):
        return await mutation()

    projection = MagicMock()
    projection.project_mutation = AsyncMock(side_effect=project_mutation)
    instance = ResourcePermissionService(
        permission_repo=mock_repo,
        organization_repo=mock_org_repo,
        user_org_repo=mock_user_org_repo,
        audit_repo=mock_audit_repo,
        authorization_projection=projection,
    )
    instance.permission_resolver = MagicMock()
    instance.permission_resolver.resolve_effective_access = AsyncMock(return_value=(["*"], True))
    return instance


@pytest.mark.asyncio
class TestResourcePermissionService:
    """Test suite for ResourcePermissionService."""

    async def test_check_returns_strongest_effective_level(
        self, service, mock_repo, mock_user_org_repo
    ):
        mock_repo.get_by_user_resource.return_value = {"permission_level": "execute"}
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": uuid.uuid4()}]
        mock_repo.get_by_org_resource.return_value = {"permission_level": "admin"}
        result = await service.check_resource_access(uuid.uuid4(), "agent", "1", "execute")
        assert result["permission_level"] == "admin"
        assert result["source"] == "organization"

    @pytest.mark.parametrize("operation", ["revoke", "downgrade"])
    async def test_manager_cannot_remove_stronger_grant(self, service, mock_repo, operation):
        from src.core.exceptions import ForbiddenError

        actor, permission_id, org = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service.permission_resolver.resolve_effective_access.return_value = (
            ["org:manage-resources"],
            False,
        )
        service.user_organization_service = MagicMock()
        service.user_organization_service.can_manage_organization = AsyncMock(return_value=True)
        service.check_resource_access = AsyncMock(
            side_effect=lambda *_args: {"allowed": _args[-1] == "execute"}
        )
        mock_repo.get_by_id.return_value = {
            "id": permission_id,
            "organization_id": org,
            "resource_type": "agent",
            "resource_id": "1",
            "resource_name": "Agent",
            "permission_level": "admin",
        }
        mock_repo.update = AsyncMock(return_value=mock_repo.get_by_id.return_value)
        with pytest.raises(ForbiddenError):
            if operation == "revoke":
                await service.revoke_permission(permission_id, actor)
            else:
                await service.update_permission(permission_id, "execute", actor)

    async def test_unscoped_grant_route_cannot_write_outside_manager_unit(self, service, mock_repo):
        from src.core.exceptions import ForbiddenError

        service.permission_resolver.resolve_effective_access.return_value = (
            ["org:manage-resources"],
            False,
        )
        service.user_organization_service = MagicMock()
        service.user_organization_service.can_manage_organization = AsyncMock(return_value=False)
        with pytest.raises(ForbiddenError):
            await service.grant_permission(
                "agent", "1", organization_id=uuid.uuid4(), granted_by=uuid.uuid4()
            )
        mock_repo.create.assert_not_awaited()

    async def test_weaker_direct_grant_does_not_mask_organization_grant(
        self, service, mock_repo, mock_user_org_repo
    ):
        mock_repo.get_by_user_resource.return_value = {"permission_level": "execute"}
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": uuid.uuid4()}]
        mock_repo.get_by_org_resource.return_value = {"permission_level": "read"}
        result = await service.check_permission(uuid.uuid4(), "rag_collection", "docs", "read")
        assert result["allowed"] is True
        assert result["source"] == "organization"

    async def test_accessible_resources_keep_strongest_grant(
        self, service, mock_repo, mock_user_org_repo
    ):
        grant = {"resource_type": "rag_collection", "resource_id": "docs"}
        mock_repo.get_user_permissions.return_value = [{**grant, "permission_level": "execute"}]
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": uuid.uuid4()}]
        mock_repo.get_organization_permissions.return_value = [
            {**grant, "permission_level": "read"}
        ]
        resources = await service.get_user_accessible_resources(uuid.uuid4(), "rag_collection")
        assert len(resources) == 1
        assert resources[0]["permission_level"] == "read"

    async def test_unknown_required_permission_is_denied(self, service, mock_repo):
        mock_repo.get_by_user_resource.return_value = {"permission_level": "read"}
        result = await service.check_permission(uuid.uuid4(), "agent", "1", "invalid")
        assert result["allowed"] is False

    async def test_organization_grant_listing_rejects_unrelated_scope(self, service, mock_org_repo):
        from src.core.exceptions import ForbiddenError
        from src.service.organization_scope_service import OrganizationScope

        service.scope_service = MagicMock()
        service.scope_service.resolve = AsyncMock(return_value=OrganizationScope(False, []))
        mock_org_repo.get_by_id.return_value = {"id": uuid.uuid4(), "path": "/"}
        with pytest.raises(ForbiddenError):
            await service.get_organization_permissions(uuid.uuid4(), actor_id=uuid.uuid4())

    async def test_grant_user_permission(self, service, mock_repo):
        """Test granting direct user permission."""
        user_id = uuid.uuid4()
        resource_id = "agent-123"
        granted_by = uuid.uuid4()

        mock_repo.create.return_value = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "organization_id": None,
            "resource_type": "agent",
            "resource_id": resource_id,
            "resource_name": resource_id,
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
        mock_repo.create.assert_called_once()

    async def test_grant_organization_permission(self, service, mock_repo):
        """Test granting organization-level permission."""
        org_id = uuid.uuid4()
        resource_id = "collection-456"
        granted_by = uuid.uuid4()

        mock_repo.create.return_value = {
            "id": uuid.uuid4(),
            "user_id": None,
            "organization_id": org_id,
            "resource_type": "rag_collection",
            "resource_id": resource_id,
            "resource_name": resource_id,
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
        mock_repo.create.assert_called_once()

    async def test_revoke_permission(self, service, mock_repo):
        """Test revoking a permission."""
        permission_id = uuid.uuid4()
        mock_repo.get_by_id.return_value = {
            "id": permission_id,
            "user_id": uuid.uuid4(),
            "organization_id": None,
            "resource_type": "agent",
            "resource_id": "agent-123",
            "resource_name": "Agent 123",
            "permission_level": "read",
        }
        mock_repo.delete.return_value = True

        result = await service.revoke_permission(permission_id)

        assert result is True
        mock_repo.delete.assert_called_once_with(permission_id)

    async def test_check_permission_direct_user(self, service, mock_repo, mock_user_org_repo):
        """Test permission check with direct user permission (highest priority)."""
        user_id = uuid.uuid4()
        resource_id = "agent-123"

        # User has direct "write" permission
        mock_repo.get_by_user_resource.return_value = {
            "permission_level": "write",
            "resource_type": "agent",
            "resource_id": resource_id,
        }

        # User is also in organization with "read" (should be ignored)
        org_id = uuid.uuid4()
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_by_org_resource.return_value = {
            "permission_level": "read",
            "resource_type": "agent",
            "resource_id": resource_id,
        }

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
        mock_repo.get_by_user_resource.return_value = None

        # User is in organization with permission
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_by_org_resource.return_value = {
            "permission_level": "read",
            "resource_type": "rag_collection",
            "resource_id": resource_id,
            "organization_id": org_id,
        }

        result = await service.check_permission(
            user_id=user_id,
            resource_type="rag_collection",
            resource_id=resource_id,
            required_permission="read",
        )

        assert result["allowed"] is True
        assert result["permission_level"] == "read"
        assert result["source"] == "organization"

    async def test_check_permission_does_not_use_ancestor_permissions(
        self, service, mock_repo, mock_user_org_repo, mock_org_repo
    ):
        """Test permission check only uses direct organization permissions."""
        user_id = uuid.uuid4()
        resource_id = "agent-789"
        child_org_id = uuid.uuid4()
        parent_org_id = uuid.uuid4()

        # No direct user permission
        mock_repo.get_by_user_resource.return_value = None

        # User is in child organization
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": child_org_id}]

        # No permission on child organization
        mock_repo.get_by_org_resource.return_value = None

        # Parent organization has permission
        mock_org_repo.get_ancestors.return_value = [{"id": parent_org_id, "name": "Parent Org"}]

        result = await service.check_permission(
            user_id=user_id,
            resource_type="agent",
            resource_id=resource_id,
            required_permission="execute",
        )

        assert result["allowed"] is False
        assert result["permission_level"] is None
        assert result["source"] is None
        mock_org_repo.get_ancestors.assert_not_awaited()

    async def test_check_permission_insufficient_level(
        self, service, mock_repo, mock_user_org_repo
    ):
        """Test permission denied when level is insufficient."""
        user_id = uuid.uuid4()
        resource_id = "collection-999"

        # User has "read" but needs "write"
        mock_repo.get_by_user_resource.return_value = {
            "permission_level": "read",
            "resource_type": "rag_collection",
            "resource_id": resource_id,
        }
        mock_user_org_repo.get_user_organizations.return_value = []

        result = await service.check_permission(
            user_id=user_id,
            resource_type="rag_collection",
            resource_id=resource_id,
            required_permission="write",
        )

        assert result["allowed"] is False
        assert result["permission_level"] == "read"

    async def test_check_permission_no_access(self, service, mock_repo, mock_user_org_repo):
        """Test permission denied when user has no access."""
        user_id = uuid.uuid4()
        resource_id = "connector-404"

        mock_repo.get_by_user_resource.return_value = None
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

    async def test_get_user_accessible_resources(
        self, service, mock_repo, mock_user_org_repo, mock_org_repo
    ):
        """Test listing all resources a user can access."""
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()

        # Direct permissions
        mock_repo.get_user_permissions.return_value = [
            {"resource_type": "agent", "resource_id": "agent-1", "permission_level": "read"},
            {"resource_type": "agent", "resource_id": "agent-2", "permission_level": "write"},
        ]

        # Organization permissions
        mock_user_org_repo.get_user_organizations.return_value = [{"organization_id": org_id}]
        mock_repo.get_organization_permissions.return_value = [
            {"resource_type": "agent", "resource_id": "agent-3", "permission_level": "execute"},
        ]
        mock_org_repo.get_ancestors.return_value = []

        result = await service.get_user_accessible_resources(user_id=user_id, resource_type="agent")

        assert len(result) == 3
        resource_ids = [r["resource_id"] for r in result]
        assert "agent-1" in resource_ids
        assert "agent-2" in resource_ids
        assert "agent-3" in resource_ids
