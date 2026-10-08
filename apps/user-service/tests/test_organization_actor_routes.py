"""Every organization operation carries the authenticated actor."""

import uuid
from unittest.mock import AsyncMock

import pytest
from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import organizations_route
from src.controller.organization_controller import OrganizationController
from src.core.exceptions import ForbiddenError
from tests.route_support import override_route_dependencies


@pytest.mark.parametrize(
    ("method", "path", "operation", "body"),
    [
        ("get", "/organizations/tree", "get_organization_tree", None),
        ("get", "/organizations", "list_organizations", None),
        ("get", "/organizations/search?q=team", "search_organizations", None),
        ("get", "/organizations/stats", "get_organization_stats", None),
        ("get", "/organizations/{id}", "get_organization", None),
        ("get", "/organizations/{id}/children", "get_organization_children", None),
        ("get", "/organizations/{id}/ancestors", "get_organization_ancestors", None),
        ("patch", "/organizations/{id}", "update_organization", {"name": "renamed"}),
        ("delete", "/organizations/{id}", "delete_organization", None),
        (
            "post",
            "/organizations/{id}/move",
            "move_organization",
            {"new_parent_id": str(uuid.uuid4())},
        ),
    ],
)
def test_organization_routes_forward_actor(monkeypatch, method, path, operation, body):
    actor = uuid.uuid4()
    controller = AsyncMock()
    getattr(controller, operation).return_value = None if method == "delete" else {}
    monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: controller)
    app = FastAPI()
    app.include_router(organizations_route.router)
    override_route_dependencies(app, lambda: str(actor))
    response = TestClient(app).request(method, path.format(id=uuid.uuid4()), json=body)
    assert response.status_code < 300
    assert getattr(controller, operation).await_args.kwargs["actor_id"] == actor


def test_scope_denial_returns_http_403(monkeypatch):
    controller = OrganizationController()
    service = AsyncMock()
    service.update_organization.side_effect = ForbiddenError(message="Outside scope")
    monkeypatch.setattr(controller, "_service", lambda _: service)
    monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: controller)
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
    app.include_router(organizations_route.router)
    override_route_dependencies(app, lambda: str(uuid.uuid4()))
    response = TestClient(app, raise_server_exceptions=False).patch(
        f"/organizations/{uuid.uuid4()}", json={"name": "Outside"}
    )
    assert response.status_code == 403
