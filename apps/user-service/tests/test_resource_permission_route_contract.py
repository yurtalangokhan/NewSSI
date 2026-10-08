"""Resource route parameters and actor forwarding match their controllers."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import resource_permissions_route
from tests.route_support import override_route_dependencies


@pytest.mark.parametrize(
    ("method", "path", "operation", "scoped"),
    [
        (
            "get",
            "/permissions/users/{id}/accessible-resources?required_permission=execute",
            "get_user_accessible_resources",
            False,
        ),
        ("get", "/permissions/users/{id}/resources", "get_user_permissions_listing", True),
        ("get", "/permissions/resources/agent/42", "get_resource_permissions", True),
        ("get", "/permissions/audit/users/{id}", "get_user_audit_logs", True),
        ("get", "/permissions/audit/organizations/{id}", "get_organization_audit_logs", True),
        ("get", "/permissions/audit/resources/agent/42", "get_resource_audit_logs", True),
        ("get", "/permissions/audit/recent", "get_recent_audit_logs", True),
        (
            "patch",
            "/permissions/permissions/{id}?permission_level=read",
            "update_permission",
            False,
        ),
    ],
)
def test_resource_route_contract(monkeypatch, method, path, operation, scoped):
    actor = uuid.uuid4()
    controller = AsyncMock()
    getattr(controller, operation).return_value = {}
    monkeypatch.setattr(
        resource_permissions_route, "get_resource_permission_controller", lambda: controller
    )
    app = FastAPI()
    app.include_router(resource_permissions_route.router)
    override_route_dependencies(app, lambda: str(actor))
    response = TestClient(app).request(method, path.format(id=uuid.uuid4()))
    assert response.status_code == 200
    if scoped:
        assert getattr(controller, operation).await_args.kwargs["actor_id"] == actor
