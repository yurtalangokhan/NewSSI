from langconnect.server import APP
from tests.unit_tests.fixtures import get_async_test_client


def _route_paths() -> set[str]:
    return {getattr(route, "path", "") for route in APP.routes}


def test_rag_service_exposes_only_api_v1_routes_without_legacy_aliases() -> None:
    paths = _route_paths()

    canonical_paths = {
        "/api/v1/health",
        "/api/v1/collections",
        "/api/v1/collections/{collection_id}",
        "/api/v1/collections/{collection_id}/documents",
        "/api/v1/datasources/knowledge-selector",
        "/api/v1/graph/build",
        "/api/v1/graph/health",
    }
    legacy_paths = {
        "/health",
        "/collections",
        "/collections/{collection_id}",
        "/collections/{collection_id}/documents",
        "/datasources/knowledge-selector",
        "/graph/build",
        "/graph/health",
    }

    assert canonical_paths <= paths
    assert legacy_paths.isdisjoint(paths)


def test_rag_service_routes_do_not_create_nested_api_prefixes() -> None:
    nested_paths = [path for path in _route_paths() if path.startswith("/api/v1/api/")]

    assert nested_paths == []


async def test_api_v1_health_is_public() -> None:
    async with get_async_test_client() as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_api_v1_readiness_is_public() -> None:
    async with get_async_test_client() as client:
        response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["service"] == "rag-service"


async def test_api_v1_readiness_returns_503_when_required_dependency_fails() -> None:
    from langconnect.observability import (
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
        async with get_async_test_client() as client:
            response = await client.get("/api/v1/health/ready")
    finally:
        dependency_registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["dependencies"]["postgres"]["status"] == "failed"
    assert response.json()["dependencies"]["postgres"]["required"] is True


async def test_api_v1_collections_requires_auth() -> None:
    async with get_async_test_client() as client:
        response = await client.get("/api/v1/collections")

    assert response.status_code == 401
