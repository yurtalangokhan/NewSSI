import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from src.api.dependencies import get_current_user_id, require_auth_or_internal_service_token
from src.api.routes import user_route
from src.main import create_app


def _route_paths() -> set[str]:
    return {getattr(route, "path", "") for route in create_app().routes}


def test_user_service_exposes_only_api_v1_routes_without_legacy_aliases() -> None:
    paths = _route_paths()

    canonical_paths = {
        "/api/v1/health/",
        "/api/v1/health/ready",
        "/api/v1/auth/type",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/users/me",
        "/api/v1/users/me/roles",
        "/api/v1/users/me/settings/",
        "/api/v1/users/me/memories",
        "/api/v1/users/me/api-keys/",
        "/api/v1/roles/",
        "/api/v1/roles/{role_name}/effective-permissions",
        "/api/v1/roles/{role_name}/inherited-roles",
        "/api/v1/coarse-roles/",
        "/api/v1/permissions/",
        "/api/v1/permissions/coverage",
        "/api/v1/permissions/check",
        (
            "/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}"
            "/resources/{resource_type}"
        ),
        "/api/v1/system-settings/keycloak",
        "/api/v1/internal/audit-logs",
        "/api/v1/internal/users/{target_id}/permissions",
        "/api/v1/internal/users/{target_id}/effective-permissions",
        "/api/v1/internal/users/{target_id}/roles",
        "/api/v1/internal/users/authorize",
        "/api/v1/users/{target_id}/roles",
        "/api/v1/users/{target_id}/roles/{role_id}",
        "/api/v1/users/{target_id}/roles/{role_id}/primary",
    }
    legacy_paths = {
        "/health/",
        "/health/ready",
        "/api/auth/type",
        "/api/users/me",
        "/api/users/internal/{target_id}/permissions",
        "/api/internal/users/{target_id}/settings",
        "/api/internal/users/{target_id}/memories",
    }

    assert canonical_paths <= paths
    assert legacy_paths.isdisjoint(paths)


def test_api_v1_routes_do_not_create_nested_api_prefixes() -> None:
    nested_paths = [path for path in _route_paths() if path.startswith("/api/v1/api/")]

    assert nested_paths == []


def test_api_v1_routes_do_not_expose_malformed_versioned_internal_aliases() -> None:
    malformed_paths = [
        path
        for path in _route_paths()
        if path.startswith("/api/v1/users/me/") and "/internal/users/" in path
    ]

    assert malformed_paths == []


def test_api_v1_health_endpoint_is_public() -> None:
    response = TestClient(create_app()).get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "user-service"}


def test_api_v1_readiness_endpoint_is_public(monkeypatch) -> None:
    import src.core.database.engine as db_engine_module

    class FakeConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConn()

    monkeypatch.setattr(db_engine_module, "get_db_engine", lambda: FakeEngine())

    response = TestClient(create_app()).get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["service"] == "user-service"


def test_api_v1_readiness_returns_503_when_required_dependency_fails(monkeypatch) -> None:
    import src.core.database.engine as db_engine_module
    from src.core.observability import DependencyPolicy, DependencyStatus, dependency_registry

    class FakeConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConn()

    monkeypatch.setattr(db_engine_module, "get_db_engine", lambda: FakeEngine())

    dependency_registry.record(
        DependencyStatus(
            name="keycloak",
            policy=DependencyPolicy.REQUIRED,
            status="failed",
        )
    )
    try:
        response = TestClient(create_app()).get("/api/v1/health/ready")
    finally:
        dependency_registry.record_ok("keycloak", policy=DependencyPolicy.REQUIRED)

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"]["keycloak"]["status"] == "failed"
    assert response.json()["dependencies"]["keycloak"]["required"] is True


def test_api_v1_auth_type_endpoint_is_public() -> None:
    response = TestClient(create_app()).get("/api/v1/auth/type")

    assert response.status_code == 200
    assert "authType" in response.json()


def test_api_v1_protected_endpoint_requires_auth() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: None

    response = TestClient(app).get("/api/v1/users/me")

    assert response.status_code == 401


def test_canonical_internal_permissions_endpoint_resolves_target_user(monkeypatch) -> None:
    target_id = uuid.uuid4()
    controller = SimpleNamespace(
        authorize_target_user_id=AsyncMock(return_value=target_id),
        get_user_permissions=AsyncMock(return_value={"permissions": ["document:read"]}),
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)

    app = create_app()
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "internal-service"

    response = TestClient(app).get(f"/api/v1/internal/users/{target_id}/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": ["document:read"]}
    controller.authorize_target_user_id.assert_awaited_once_with(
        str(target_id),
        "internal-service",
    )
    controller.get_user_permissions.assert_awaited_once_with(target_id)
