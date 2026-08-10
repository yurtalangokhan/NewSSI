"""
Tests for organization API routes.

Tests REST endpoints for hierarchical organization management.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.organizations_route import router as organizations_router
from src.core.exceptions import ConflictError


@pytest.fixture
def app():
    """FastAPI app with organizations router."""
    app = FastAPI()
    app.include_router(organizations_router)
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant:
            for dependency in dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: str(uuid.uuid4())
    return app


@pytest.fixture
def client(app):
    """Test client."""
    return TestClient(app)


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user for dependency injection."""
    return {
        "user_id": str(uuid.uuid4()),
        "email": "admin@example.com",
        "is_superuser": True,
    }


@pytest.fixture
def mock_service():
    """Mock OrganizationService."""
    service = MagicMock()
    service.create_organization = AsyncMock()
    service.get_organization = AsyncMock()
    service.update_organization = AsyncMock()
    service.delete_organization = AsyncMock()
    service.list_organizations = AsyncMock()
    service.get_organization_children = AsyncMock()
    service.get_organization_tree = AsyncMock()
    service.move_organization = AsyncMock()
    service.can_manage_organization = AsyncMock()
    return service


class TestOrganizationRoutes:
    """Test suite for organization API routes."""

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_create_organization(self, mock_get_service, client, mock_service):
        """Test POST /organizations - create organization."""
        mock_get_service.return_value = mock_service

        org_id = uuid.uuid4()
        mock_service.create_organization.return_value = {
            "id": str(org_id),
            "name": "Engineering",
            "parent_id": None,
            "path": f"{org_id}/",
            "description": "Engineering department",
        }

        response = client.post(
            "/organizations",
            json={
                "name": "Engineering",
                "code": "engineering",
                "description": "Engineering department",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Engineering"
        assert data["parent_id"] is None

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_create_child_organization(self, mock_get_service, client, mock_service):
        """Test creating a child organization."""
        mock_get_service.return_value = mock_service

        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()

        mock_service.create_organization.return_value = {
            "id": str(child_id),
            "name": "Backend Team",
            "parent_id": str(parent_id),
            "path": f"{parent_id}/{child_id}/",
        }

        response = client.post(
            "/organizations",
            json={
                "name": "Backend Team",
                "code": "backend-team",
                "parent_id": str(parent_id),
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Backend Team"
        assert data["parent_id"] == str(parent_id)

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_create_organization_translates_root_conflict(
        self, mock_get_service, client, mock_service
    ):
        """Database-enforced single-root conflicts are returned as HTTP 409."""
        mock_get_service.return_value = mock_service
        mock_service.create_organization.side_effect = ConflictError(
            "A root organization already exists"
        )

        response = client.post(
            "/organizations",
            json={"name": "Second root", "code": "second-root"},
        )

        assert response.status_code == 409
        assert response.json() == {"detail": "A root organization already exists"}

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_organization(self, mock_get_service, client, mock_service):
        """Test GET /organizations/{id} - get organization by ID."""
        mock_get_service.return_value = mock_service

        org_id = uuid.uuid4()
        mock_service.get_organization.return_value = {
            "id": str(org_id),
            "name": "Marketing",
            "parent_id": None,
            "path": f"{org_id}/",
        }

        response = client.get(f"/organizations/{org_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Marketing"

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_organization_not_found(self, mock_get_service, client, mock_service):
        """Test GET /organizations/{id} with non-existent ID."""
        mock_get_service.return_value = mock_service

        mock_service.get_organization.return_value = None

        response = client.get(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 404

    @patch("src.api.routes.organizations_route.get_user_organization_service")
    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_management_capability(
        self, mock_get_org_service, mock_get_membership_service, client, mock_service
    ):
        """Return the actor's edit capability for an existing organization."""
        org_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_service.get_organization.return_value = {"id": str(org_id)}
        mock_get_org_service.return_value = mock_service
        membership_service = MagicMock()
        membership_service.can_manage_organization = AsyncMock(return_value=True)
        mock_get_membership_service.return_value = membership_service

        response = client.get(
            f"/organizations/{org_id}/management-capability",
            headers={"X-Test-Actor": str(actor_id)},
        )

        assert response.status_code == 200
        assert response.json() == {"editable": True}
        membership_service.can_manage_organization.assert_awaited_once()

    @patch("src.api.routes.organizations_route.get_user_organization_service")
    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_management_capability_returns_404_for_missing_organization(
        self, mock_get_org_service, mock_get_membership_service, client, mock_service
    ):
        """Do not expose a capability for an organization that does not exist."""
        mock_service.get_organization.return_value = None
        mock_get_org_service.return_value = mock_service

        response = client.get(f"/organizations/{uuid.uuid4()}/management-capability")

        assert response.status_code == 404
        mock_get_membership_service.assert_not_called()

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_update_organization(self, mock_get_service, client, mock_service):
        """Test PATCH /organizations/{id} - update organization."""
        mock_get_service.return_value = mock_service

        org_id = uuid.uuid4()
        mock_service.update_organization.return_value = {
            "id": str(org_id),
            "name": "Updated Name",
            "description": "Updated description",
        }

        response = client.patch(
            f"/organizations/{org_id}",
            json={"name": "Updated Name", "description": "Updated description"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_delete_organization(self, mock_get_service, client, mock_service):
        """Test DELETE /organizations/{id} - delete organization."""
        mock_get_service.return_value = mock_service

        mock_service.delete_organization.return_value = True

        response = client.delete(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 204

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_delete_organization_with_children(self, mock_get_service, client, mock_service):
        """Test DELETE fails when organization has children."""
        mock_get_service.return_value = mock_service

        mock_service.delete_organization.side_effect = ValueError("Organization has children")

        response = client.delete(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 400

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_list_organizations(self, mock_get_service, client, mock_service):
        """Test GET /organizations - list all organizations."""
        mock_get_service.return_value = mock_service

        mock_service.list_organizations.return_value = (
            [
                {"id": str(uuid.uuid4()), "name": "Org 1"},
                {"id": str(uuid.uuid4()), "name": "Org 2"},
            ],
            2,
        )

        response = client.get("/organizations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_organization_tree(self, mock_get_service, client, mock_service):
        """Test GET /organizations/tree - get hierarchical tree."""
        mock_get_service.return_value = mock_service

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()

        mock_service.get_organization_tree.return_value = [
            {
                "id": str(root_id),
                "name": "Root",
                "children": [{"id": str(child_id), "name": "Child", "children": []}],
            }
        ]

        response = client.get("/organizations/tree")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Root"
        assert len(data[0]["children"]) == 1

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_move_organization(self, mock_get_service, client, mock_service):
        """Test POST /organizations/{id}/move - move organization."""
        mock_get_service.return_value = mock_service

        org_id = uuid.uuid4()
        new_parent_id = uuid.uuid4()

        mock_service.move_organization.return_value = {
            "id": str(org_id),
            "parent_id": str(new_parent_id),
            "path": f"{new_parent_id}/{org_id}/",
        }

        response = client.post(
            f"/organizations/{org_id}/move", json={"parent_id": str(new_parent_id)}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["parent_id"] == str(new_parent_id)

    @patch("src.api.routes.organizations_route.get_organization_service")
    def test_get_children(self, mock_get_service, client, mock_service):
        """Test GET /organizations/{id}/children - get direct children."""
        mock_get_service.return_value = mock_service

        parent_id = uuid.uuid4()
        mock_service.get_organization_children.return_value = [
            {"id": str(uuid.uuid4()), "name": "Child 1"},
            {"id": str(uuid.uuid4()), "name": "Child 2"},
        ]

        response = client.get(f"/organizations/{parent_id}/children")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
