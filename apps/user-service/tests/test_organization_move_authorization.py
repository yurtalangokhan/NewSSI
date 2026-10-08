"""Verify move action authorization without mutating organization data."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import register_error_handlers
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.routes import organizations_route


@pytest.mark.parametrize(
    ("permissions", "is_admin", "status"),
    [
        ([], True, 403),
        (["org:move"], True, 200),
        (["org:move"], False, 200),
        (["*"], False, 200),
        (["org:update"], False, 403),
        ([], False, 403),
    ],
)
def test_move_requires_configured_permission(monkeypatch, permissions, is_admin, status):
    actor_id, organization_id, parent_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    resolver = SimpleNamespace(
        resolve_effective_permissions=AsyncMock(return_value=permissions),
        resolve_effective_access=AsyncMock(return_value=(permissions, is_admin)),
    )
    user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=actor_id, role="admin")),
        exists_by_id=AsyncMock(return_value=True),
    )
    monkeypatch.setattr("src.repository.UserRepository", lambda: user_repo)
    monkeypatch.setattr(dependencies, "get_permission_resolver_service", lambda: resolver)
    monkeypatch.setattr("src.service.get_audit_service", lambda: SimpleNamespace(log=AsyncMock()))
    controller = SimpleNamespace(move_organization=AsyncMock(return_value={"moved": True}))
    monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: controller)
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
    app.include_router(organizations_route.router)
    app.dependency_overrides[dependencies.require_auth] = lambda: str(actor_id)

    with TestClient(app) as client:
        response = client.post(
            f"/organizations/{organization_id}/move",
            json={"new_parent_id": str(parent_id)},
        )

    assert response.status_code == status
    if status == 200:
        controller.move_organization.assert_awaited_once_with(
            organization_id, parent_id, actor_id=actor_id
        )
    else:
        controller.move_organization.assert_not_awaited()
