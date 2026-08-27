"""
Characterization tests for the standardized error response contract.

These tests lock the exact HTTP envelope returned by representative auth,
user, organization, role, permission, and validation error paths before
route and service refactors.  No implementation code is changed — these
tests exist purely as a safety net for later refactors.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from error_contract import register_error_handlers
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.routes import organizations_route, permissions_route, resource_permissions_route
from src.api.routes import roles_route as roles_router_module
from src.api.routes import user_route as user_route_module
from src.controller.resource_permission_controller import ResourcePermissionController
from src.core.exceptions import ForbiddenError, NotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SERVICE_NAME = "user-service-test"


def _make_app(*routers: FastAPI | object) -> FastAPI:
    """Build a FastAPI app with registered error handlers and the given routers."""
    app = FastAPI()
    register_error_handlers(app, service_name=_SERVICE_NAME)
    for router in routers:
        app.include_router(router)
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant:
            for dependency in dependant.dependencies:
                app.dependency_overrides[dependency.call] = lambda: str(uuid.uuid4())
    return app


def _assert_envelope(
    body: dict,
    *,
    expected_code: str,
    expected_status: int,
    message_contains: str | None = None,
) -> None:
    """Assert a response body is a valid standardized error envelope."""
    assert "error" in body, f"Missing 'error' key in response: {body}"
    error = body["error"]
    assert error["code"] == expected_code, f"Expected code {expected_code!r}, got {error['code']!r}"
    assert isinstance(error["message"], str) and error["message"], (
        "error.message must be a non-empty string"
    )
    assert isinstance(error["details"], dict), "error.details must be a dict"
    assert isinstance(error["field_errors"], list), "error.field_errors must be a list"
    assert "request_id" in error, "error.request_id must be present"
    if message_contains:
        assert message_contains in error["message"], (
            f"Expected {message_contains!r} in message, got {error['message']!r}"
        )


# ===========================================================================
# Auth
# ===========================================================================


class TestAuthErrorContract:
    """An unauthenticated request to a protected endpoint returns a 401 envelope."""

    def test_protected_endpoint_without_credentials_returns_unauthorized_envelope(self) -> None:
        """No credentials → 401 auth.unauthorized with the standard envelope."""
        # Build a minimal app WITHOUT overriding auth dependencies so the
        # real dependency chain fires and returns 401.
        from src.api.dependencies import get_current_user_id

        app = FastAPI()
        register_error_handlers(app, service_name=_SERVICE_NAME)
        app.include_router(organizations_route.router)
        app.dependency_overrides[get_current_user_id] = lambda: None

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/organizations")

        assert response.status_code == 401
        _assert_envelope(response.json(), expected_code="auth.unauthorized", expected_status=401)

    def test_protected_endpoint_without_credentials_has_stable_envelope_shape(self) -> None:
        """The 401 envelope carries exactly the five standard keys."""
        from src.api.dependencies import get_current_user_id

        app = FastAPI()
        register_error_handlers(app, service_name=_SERVICE_NAME)
        app.include_router(organizations_route.router)
        app.dependency_overrides[get_current_user_id] = lambda: None

        body = TestClient(app, raise_server_exceptions=False).get("/organizations").json()

        error = body["error"]
        # Every envelope must carry these five keys regardless of error kind
        assert set(error.keys()) == {"code", "message", "details", "field_errors", "request_id"}


# ===========================================================================
# User
# ===========================================================================


class TestUserErrorContract:
    """User controller failures translate to the correct envelope codes."""

    def test_user_route_bad_request_returns_400_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Controller raising HTTPException(400) maps to 400 request.invalid.

        User routes delegate to controllers which raise HTTPException for
        domain errors.  The error handler translates the detail string into
        the standardized envelope.
        """
        from fastapi import HTTPException as _HTTPExc

        ctrl = MagicMock()
        ctrl.create_user = AsyncMock(
            side_effect=_HTTPExc(status_code=400, detail="email is required")
        )
        monkeypatch.setattr(user_route_module, "get_user_controller", lambda: ctrl)

        app = _make_app(user_route_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        # Must provide all required fields so Pydantic validation passes
        # and the controller's HTTPException is what triggers the 400.
        response = client.post(
            "/users/",
            json={"email": "test@example.com", "first_name": "A", "last_name": "B"},
        )

        assert response.status_code == 400
        _assert_envelope(
            response.json(),
            expected_code="request.invalid",
            expected_status=400,
            message_contains="email is required",
        )

    def test_user_route_not_found_returns_404_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing user maps to 404 request.not_found.

        The controller catches None from the service and raises HTTPException(404),
        which the error handler translates to the standardized envelope.
        """
        mock_user_service = MagicMock()
        mock_user_service.get_user = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "src.controller.user_controller.get_user_service", lambda: mock_user_service
        )

        # Force re-creation of the singleton so it picks up the mock
        import src.controller.user_controller as uc_module

        uc_module._user_controller = None

        app = _make_app(user_route_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(f"/users/{uuid.uuid4()}")

        assert response.status_code == 404
        _assert_envelope(
            response.json(),
            expected_code="request.not_found",
            expected_status=404,
            message_contains="not found",
        )

        # Restore singleton
        uc_module._user_controller = None

    def test_user_route_forbidden_error_returns_403_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ForbiddenError from the service maps to 403 auth.forbidden.

        The controller catches ForbiddenError and raises HTTPException(403),
        which the error handler translates to the standardized envelope.
        """
        from src.core.exceptions import ForbiddenError as DomainForbiddenError

        mock_user_service = MagicMock()
        mock_user_service.update_user = AsyncMock(
            side_effect=DomainForbiddenError("Cannot modify admin user")
        )
        monkeypatch.setattr(
            "src.controller.user_controller.get_user_service", lambda: mock_user_service
        )

        # Force re-creation of the singleton so it picks up the mock
        import src.controller.user_controller as uc_module

        uc_module._user_controller = None

        app = _make_app(user_route_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.patch(f"/users/{uuid.uuid4()}", json={"first_name": "X"})

        assert response.status_code == 403
        _assert_envelope(
            response.json(),
            expected_code="auth.forbidden",
            expected_status=403,
        )

        # Restore singleton
        uc_module._user_controller = None


# ===========================================================================
# Organization
# ===========================================================================


class TestOrganizationErrorContract:
    """Organization routes return the standardized envelope for domain errors."""

    def test_organization_not_found_returns_404_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing organization maps to 404 with the standard envelope."""
        ctrl = MagicMock()
        ctrl.get_organization = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Organization not found")
        )
        monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: ctrl)

        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 404
        _assert_envelope(response.json(), expected_code="request.not_found", expected_status=404)

    def test_organization_delete_with_children_returns_400_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ValueError (has children) from the delete path maps to 400."""
        ctrl = MagicMock()
        ctrl.delete_organization = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Organization has children")
        )
        monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: ctrl)

        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.delete(f"/organizations/{uuid.uuid4()}")

        assert response.status_code == 400
        _assert_envelope(response.json(), expected_code="request.invalid", expected_status=400)

    def test_organization_not_found_envelope_has_stable_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """404 envelope carries the five standard keys."""
        ctrl = MagicMock()
        ctrl.get_organization = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Organization not found")
        )
        monkeypatch.setattr(organizations_route, "get_organization_controller", lambda: ctrl)

        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        body = client.get(f"/organizations/{uuid.uuid4()}").json()
        error = body["error"]

        assert set(error.keys()) == {"code", "message", "details", "field_errors", "request_id"}

    def test_organization_create_without_required_fields_returns_422_envelope(self) -> None:
        """Missing required body fields trigger 422 validation.failed."""
        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/organizations", json={"description": "no name or code"})

        assert response.status_code == 422
        _assert_envelope(response.json(), expected_code="validation.failed", expected_status=422)

    def test_organization_create_validation_envelope_has_field_errors(self) -> None:
        """The 422 envelope carries per-field errors in field_errors."""
        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        body = client.post("/organizations", json={}).json()
        field_errors = body["error"]["field_errors"]

        assert len(field_errors) > 0, "Expected at least one field error for missing name/code"
        for fe in field_errors:
            assert "field" in fe
            assert "code" in fe
            assert "message" in fe


# ===========================================================================
# Role
# ===========================================================================


class TestRoleErrorContract:
    """Role controller errors translate through the standardized envelope."""

    def test_role_get_not_found_returns_404_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_role returning None maps to 404 with role.not_found."""
        ctrl = MagicMock()
        ctrl.get_role = AsyncMock(return_value=None)
        # _raise_not_found reads the controller's i18n; mock the HTTPException directly
        from fastapi import HTTPException as _HTTPExc

        ctrl.get_role.side_effect = _HTTPExc(status_code=404, detail="Role 'missing' not found")
        monkeypatch.setattr(roles_router_module, "get_composite_role_controller", lambda: ctrl)

        app = _make_app(roles_router_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/roles/missing")

        assert response.status_code == 404
        _assert_envelope(
            response.json(),
            expected_code="request.not_found",
            expected_status=404,
        )

    def test_role_create_conflict_returns_409_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """create_role with a duplicate name maps to 409 request.conflict."""
        ctrl = MagicMock()
        ctrl.create_role = AsyncMock(side_effect=ValueError("Role 'admin' already exists"))
        # The controller catches ValueError and raises HTTPException(409)
        from fastapi import HTTPException as _HTTPExc

        ctrl.create_role.side_effect = _HTTPExc(
            status_code=409, detail="Role 'admin' already exists"
        )
        monkeypatch.setattr(roles_router_module, "get_composite_role_controller", lambda: ctrl)

        app = _make_app(roles_router_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/roles/", params={"name": "admin"})

        assert response.status_code == 409
        _assert_envelope(
            response.json(),
            expected_code="request.conflict",
            expected_status=409,
            message_contains="already exists",
        )


# ===========================================================================
# Permission
# ===========================================================================


class TestPermissionErrorContract:
    """Permission routes return the standardized envelope for domain errors."""

    def test_permission_catalog_not_found_returns_404_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_permission for a missing catalog entry maps to 404."""
        ctrl = MagicMock()
        ctrl.get_permission = AsyncMock(return_value=None)
        # BaseController._raise_not_found raises HTTPException(404)
        from fastapi import HTTPException as _HTTPExc

        ctrl.get_permission.side_effect = _HTTPExc(
            status_code=404, detail="Permission 'missing:perm' not found"
        )
        monkeypatch.setattr(permissions_route, "get_permission_controller", lambda: ctrl)

        app = _make_app(permissions_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/permissions/missing:perm")

        assert response.status_code == 404
        _assert_envelope(response.json(), expected_code="request.not_found", expected_status=404)

    def test_resource_permission_forbidden_returns_403_envelope(self) -> None:
        """ForbiddenError from the scoped permission route maps to 403."""
        org_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        service = MagicMock()
        service.get_scoped_direct_permissions = AsyncMock(
            side_effect=ForbiddenError("Not an organization manager")
        )
        ctrl = ResourcePermissionController()
        ctrl.service = service
        with patch.object(
            resource_permissions_route, "get_resource_permission_controller", lambda: ctrl
        ):
            app = _make_app(resource_permissions_route.router)
            app.dependency_overrides.clear()
            from src.api.dependencies import require_auth

            app.dependency_overrides[require_auth] = lambda: str(actor_id)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.get(
                f"/permissions/organizations/{org_id}/targets/organization/{org_id}/resources/agent"
            )

        assert response.status_code == 403
        _assert_envelope(response.json(), expected_code="auth.forbidden", expected_status=403)

    def test_resource_permission_not_found_returns_404_envelope(self) -> None:
        """NotFoundError from the scoped permission route maps to 404."""
        org_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        service = MagicMock()
        service.get_scoped_direct_permissions = AsyncMock(
            side_effect=NotFoundError("Organization not found")
        )
        ctrl = ResourcePermissionController()
        ctrl.service = service
        with patch.object(
            resource_permissions_route, "get_resource_permission_controller", lambda: ctrl
        ):
            app = _make_app(resource_permissions_route.router)
            app.dependency_overrides.clear()
            from src.api.dependencies import require_auth

            app.dependency_overrides[require_auth] = lambda: str(actor_id)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.get(
                f"/permissions/organizations/{org_id}/targets/organization/{org_id}/resources/agent"
            )

        assert response.status_code == 404
        _assert_envelope(response.json(), expected_code="request.not_found", expected_status=404)


# ===========================================================================
# Validation
# ===========================================================================


class TestValidationErrorContract:
    """Request body validation failures return 422 with field_errors."""

    def test_missing_required_fields_returns_422_validation_envelope(self) -> None:
        """Sending an empty body to a required-field endpoint returns 422."""
        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/organizations", json={})

        assert response.status_code == 422
        _assert_envelope(response.json(), expected_code="validation.failed", expected_status=422)

    def test_validation_envelope_field_errors_are_non_empty(self) -> None:
        """field_errors must list at least one failing field."""
        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        body = client.post("/organizations", json={}).json()
        field_errors = body["error"]["field_errors"]

        assert len(field_errors) > 0
        # Each field error must carry the three required keys
        for fe in field_errors:
            assert set(fe.keys()) >= {"field", "code", "message"}

    def test_validation_envelope_includes_field_path(self) -> None:
        """Each field error locates the failing field in dot-separated notation."""
        app = _make_app(organizations_route.router)
        client = TestClient(app, raise_server_exceptions=False)

        body = client.post("/organizations", json={}).json()
        field_names = [fe["field"] for fe in body["error"]["field_errors"]]

        # name and code are required in OrganizationCreateRequest
        assert any("name" in f for f in field_names), (
            f"Expected 'name' in field paths: {field_names}"
        )
        assert any("code" in f for f in field_names), (
            f"Expected 'code' in field paths: {field_names}"
        )
