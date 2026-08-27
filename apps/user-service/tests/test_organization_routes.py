"""
Tests for organization API routes.

Tests REST endpoints for hierarchical organization management.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.organizations_route import router as organizations_router


@pytest.fixture
def app():
    """FastAPI app with organizations router."""
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
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
def mock_controller():
    """Mock OrganizationController."""
    ctrl = MagicMock()
    ctrl.list_organizations = AsyncMock()
    ctrl.create_organization = AsyncMock()
    ctrl.get_organization_tree = AsyncMock()
    ctrl.get_organization_stats = AsyncMock()
    ctrl.search_organizations = AsyncMock()
    ctrl.get_organization = AsyncMock()
    ctrl.get_management_capability = AsyncMock()
    ctrl.update_organization = AsyncMock()
    ctrl.delete_organization = AsyncMock()
    ctrl.move_organization = AsyncMock()
    ctrl.get_organization_children = AsyncMock()
    ctrl.get_organization_ancestors = AsyncMock()
    return ctrl


class TestOrganizationRoutes:
    """Test suite for organization API routes."""

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_create_organization(self, mock_get_ctrl, client, mock_controller):
        """Test POST /organizations - create organization."""
        mock_get_ctrl.return_value = mock_controller

        org_id = uuid.uuid4()
        mock_controller.create_organization.return_value = {
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

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_create_child_organization(self, mock_get_ctrl, client, mock_controller):
        """Test creating a child organization."""
        mock_get_ctrl.return_value = mock_controller

        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()

        mock_controller.create_organization.return_value = {
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

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_create_organization_translates_root_conflict(
        self, mock_get_ctrl, client, mock_controller
    ):
        """Database-enforced single-root conflicts are returned as HTTP 409."""
        from fastapi import HTTPException

        mock_get_ctrl.return_value = mock_controller
        mock_controller.create_organization.side_effect = HTTPException(
            status_code=409, detail="A root organization already exists"
        )

        response = client.post(
            "/organizations",
            json={"name": "Second root", "code": "second-root"},
        )

        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "request.conflict",
                "message": "A root organization already exists",
                "details": {},
                "field_errors": [],
                "request_id": None,
            }
        }

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_organization(self, mock_get_ctrl, client, mock_controller):
        """Test GET /organizations/{id} - get organization by ID."""
        mock_get_ctrl.return_value = mock_controller

        org_id = uuid.uuid4()
        mock_controller.get_organization.return_value = {
            "id": str(org_id),
            "name": "Marketing",
            "parent_id": None,
            "path": f"{org_id}/",
        }

        response = client.get(f"/organizations/{org_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Marketing"

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_organization_not_found(self, mock_get_ctrl, client, mock_controller):
        """Test GET /organizations/{id} with non-existent ID."""
        from fastapi import HTTPException

        mock_get_ctrl.return_value = mock_controller
        mock_controller.get_organization.side_effect = HTTPException(
            status_code=404, detail="Organization not found"
        )

        response = client.get(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 404

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_management_capability(self, mock_get_ctrl, client, mock_controller):
        """Return the actor's edit capability for an existing organization."""
        org_id = uuid.uuid4()
        mock_get_ctrl.return_value = mock_controller
        mock_controller.get_management_capability.return_value = {"editable": True}

        response = client.get(
            f"/organizations/{org_id}/management-capability",
        )

        assert response.status_code == 200
        assert response.json() == {"editable": True}

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_management_capability_returns_404_for_missing_organization(
        self, mock_get_ctrl, client, mock_controller
    ):
        """Do not expose a capability for an organization that does not exist."""
        from fastapi import HTTPException

        mock_get_ctrl.return_value = mock_controller
        mock_controller.get_management_capability.side_effect = HTTPException(
            status_code=404, detail="Organization not found"
        )

        response = client.get(f"/organizations/{uuid.uuid4()}/management-capability")

        assert response.status_code == 404

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_update_organization(self, mock_get_ctrl, client, mock_controller):
        """Test PATCH /organizations/{id} - update organization."""
        mock_get_ctrl.return_value = mock_controller

        org_id = uuid.uuid4()
        mock_controller.update_organization.return_value = {
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

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_delete_organization(self, mock_get_ctrl, client, mock_controller):
        """Test DELETE /organizations/{id} - delete organization."""
        mock_get_ctrl.return_value = mock_controller

        mock_controller.delete_organization.return_value = None

        response = client.delete(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 204

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_delete_organization_with_children(self, mock_get_ctrl, client, mock_controller):
        """Test DELETE fails when organization has children."""
        from fastapi import HTTPException

        mock_get_ctrl.return_value = mock_controller
        mock_controller.delete_organization.side_effect = HTTPException(
            status_code=400, detail="Organization has children"
        )

        response = client.delete(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 400

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_list_organizations(self, mock_get_ctrl, client, mock_controller):
        """Test GET /organizations - list all organizations."""
        mock_get_ctrl.return_value = mock_controller

        mock_controller.list_organizations.return_value = {
            "items": [
                {"id": str(uuid.uuid4()), "name": "Org 1"},
                {"id": str(uuid.uuid4()), "name": "Org 2"},
            ],
            "total": 2,
            "skip": 0,
            "limit": 100,
        }

        response = client.get("/organizations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_organization_tree(self, mock_get_ctrl, client, mock_controller):
        """Test GET /organizations/tree - get hierarchical tree."""
        mock_get_ctrl.return_value = mock_controller

        root_id = uuid.uuid4()
        child_id = uuid.uuid4()

        mock_controller.get_organization_tree.return_value = [
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

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_move_organization(self, mock_get_ctrl, client, mock_controller):
        """Test POST /organizations/{id}/move - move organization."""
        mock_get_ctrl.return_value = mock_controller

        org_id = uuid.uuid4()
        new_parent_id = uuid.uuid4()

        mock_controller.move_organization.return_value = {
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

    @patch("src.api.routes.organizations_route.get_organization_controller")
    def test_get_children(self, mock_get_ctrl, client, mock_controller):
        """Test GET /organizations/{id}/children - get direct children."""
        mock_get_ctrl.return_value = mock_controller

        mock_controller.get_organization_children.return_value = {
            "children": [
                {"id": str(uuid.uuid4()), "name": "Child 1"},
                {"id": str(uuid.uuid4()), "name": "Child 2"},
            ],
            "count": 2,
        }

        response = client.get(f"/organizations/{uuid.uuid4()}/children")

        assert response.status_code == 200
        data = response.json()
        assert len(data["children"]) == 2
