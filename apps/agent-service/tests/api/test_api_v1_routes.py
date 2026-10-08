from fastapi.testclient import TestClient

from app import app
from tests.gateway_auth import use_gateway_auth


def _route_paths() -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def _protected_client(monkeypatch) -> TestClient:
    """A client that did not traverse Gateway: no trusted identity headers."""
    use_gateway_auth(monkeypatch)
    return TestClient(app)


def test_agent_service_exposes_only_api_v1_routes_without_legacy_aliases() -> None:
    paths = _route_paths()

    canonical_paths = {
        "/api/v1/health",
        "/api/v1/chat/messages",
        "/api/v1/chat/sessions",
        "/api/v1/chat/sessions/{chat_session_id}",
        "/api/v1/admin/providers",
        "/api/v1/agents/info",
        "/api/v1/agents/catalog",
        "/api/v1/agents/{agent_id}",
        "/api/v1/assistants/search",
        "/api/v1/threads/search",
        "/api/v1/datasources/connectors",
        "/api/v1/mcp-providers",
        "/api/v1/mcp-tools",
        "/api/v1/proxy/mcp/tools",
        "/api/v1/ingest/source-preview",
        "/api/v1/user/projects",
    }
    legacy_paths = {
        "/health",
        "/api/health",
        "/api/chat/get-user-chat-sessions",
        "/api/chat/messages",
        "/api/admin/providers",
        "/agents/info",
        "/assistants/search",
        "/threads/search",
        "/datasources/connectors",
        "/mcp-providers",
        "/mcp-tools",
        "/api/proxy/mcp/tools",
        "/source-preview",
        "/api/v1/ingest/batch",
        "/api/user/projects",
    }

    assert canonical_paths <= paths
    assert legacy_paths.isdisjoint(paths)


def test_unused_auth_routes_are_not_served() -> None:
    """Web reads the current user from user-service; nothing called these."""
    removed = {
        "/api/v1/auth/me",
        "/api/v1/auth/settings",
        "/api/v1/auth/enterprise-settings",
        "/api/v1/auth/health",
    }

    assert removed.isdisjoint(_route_paths())


def test_agent_service_routes_do_not_create_nested_api_prefixes() -> None:
    nested_paths = [path for path in _route_paths() if path.startswith("/api/v1/api/")]

    assert nested_paths == []


def test_api_v1_health_endpoint_is_public() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_v1_readiness_endpoint_is_public() -> None:
    from core.observability.observability import dependency_registry

    # The readiness endpoint is public (no auth gate). The registry must hold a
    # healthy required dependency for the 200/ready body: an empty registry
    # correctly reports not_ready (503), because "nothing checked yet" is not
    # the same as "ready" - the pre-consolidation copies reported green over an
    # empty map, which is the defect the shared core fixes. Recording here is
    # safe to leave behind: the 503 test below sets its own registry state.
    dependency_registry.record_ok("postgres")

    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["service"] == "agent-service"


def test_api_v1_readiness_returns_503_when_required_dependency_fails() -> None:
    from core.observability.observability import (
        DependencyPolicy,
        DependencyStatus,
        dependency_registry,
    )

    dependency_registry.record(
        DependencyStatus(
            name="postgres",
            policy=DependencyPolicy.REQUIRED,
            status="failed",
        )
    )
    try:
        response = TestClient(app).get("/api/v1/health/ready")
    finally:
        dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"]["postgres"]["status"] == "failed"
    assert response.json()["dependencies"]["postgres"]["required"] is True


def test_api_v1_protected_chat_route_requires_auth(monkeypatch) -> None:
    response = _protected_client(monkeypatch).get("/api/v1/chat/sessions")

    assert response.status_code == 401


def test_api_v1_protected_admin_route_requires_auth(monkeypatch) -> None:
    response = _protected_client(monkeypatch).get("/api/v1/admin/providers")

    assert response.status_code == 401


def test_api_v1_protected_root_resource_route_requires_auth(monkeypatch) -> None:
    response = _protected_client(monkeypatch).get("/api/v1/agents/info")

    assert response.status_code == 401
