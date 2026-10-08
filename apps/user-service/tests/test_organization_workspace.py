"""Organization views authorize before fetching caller-visible catalogs."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.repository.resource_catalog_client import ResourceCatalogClient
from src.service.organization_workspace_service import OrganizationWorkspaceService


def test_workspace_route_forwards_bearer_and_serializes_resources(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.dependencies import require_auth
    from src.api.routes import resource_permissions_route as routes

    actor, org = uuid.uuid4(), uuid.uuid4()
    controller = MagicMock(
        get_workspace=AsyncMock(
            return_value={
                "resources": [{"id": "7", "name": "Research"}],
                "permissions": [],
                "count": 0,
            }
        )
    )
    monkeypatch.setattr(routes, "get_organization_workspace_controller", lambda: controller)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_auth] = lambda: str(actor)
    response = TestClient(app).get(
        f"/permissions/organizations/{org}/targets/organization/{org}/resources/agent/workspace",
        headers={"Authorization": "Bearer jwt"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["resources"][0]["id"] == "7"
    assert controller.get_workspace.await_args.kwargs == {
        "actor_id": actor,
        "organization_id": org,
        "target_type": "organization",
        "target_id": org,
        "resource_type": "agent",
        "access_token": "jwt",
    }


@pytest.mark.parametrize("status", [302, 500])
async def test_catalog_upstream_failure_is_unavailable(monkeypatch, status):
    from src.repository.resource_catalog_client import CatalogUnavailableError

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, headers={"location": "https://elsewhere.example"}
            )
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(CatalogUnavailableError):
        await ResourceCatalogClient("https://gateway.example").list_resources("agent", "jwt")


@pytest.mark.parametrize("payload", [{}, [{"name": "Missing ID"}], [{"id": True, "name": "Bad"}]])
async def test_catalog_malformed_payload_is_unavailable(monkeypatch, payload):
    from src.repository.resource_catalog_client import CatalogUnavailableError

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(CatalogUnavailableError):
        await ResourceCatalogClient("https://gateway.example").list_resources("agent", "jwt")


async def test_workspace_combines_catalog_and_scoped_assignments():
    permissions = MagicMock()
    assignments = [{"resource_id": "7", "permission_level": "read"}]
    permissions.get_scoped_direct_permissions = AsyncMock(return_value=assignments)
    catalog = MagicMock()
    resources = [{"id": "7", "name": "Research"}]
    catalog.list_resources = AsyncMock(return_value=resources)
    service = OrganizationWorkspaceService(permissions, catalog)
    actor, org = uuid.uuid4(), uuid.uuid4()

    result = await service.get_workspace(actor, org, "organization", org, "agent", "user-jwt")

    assert result == {"resources": resources, "permissions": assignments, "count": 1}
    permissions.get_scoped_direct_permissions.assert_awaited_once_with(
        actor_id=actor,
        organization_id=org,
        target_type="organization",
        target_id=org,
        resource_type="agent",
    )
    catalog.list_resources.assert_awaited_once_with("agent", "user-jwt")


async def test_denied_organization_never_fetches_catalog():
    permissions = MagicMock()
    permissions.get_scoped_direct_permissions = AsyncMock(
        side_effect=ForbiddenError(message="denied")
    )
    catalog = MagicMock(list_resources=AsyncMock())
    service = OrganizationWorkspaceService(permissions, catalog)
    with pytest.raises(ForbiddenError):
        await service.get_workspace(
            uuid.uuid4(), uuid.uuid4(), "user", uuid.uuid4(), "agent", "jwt"
        )
    catalog.list_resources.assert_not_awaited()


@pytest.mark.parametrize(
    ("resource_type", "path", "payload", "expected"),
    [
        (
            "agent",
            "/agent-service/api/v1/persona/options",
            [
                {"id": 7, "name": "Research", "description": "Find sources"},
                {"id": 7, "name": "Duplicate"},
            ],
            [{"id": "7", "name": "Research", "description": "Find sources"}],
        ),
        (
            "rag_collection",
            "/rag-service/api/v1/collections",
            [{"uuid": "collection-1", "name": "Policies"}],
            [{"id": "collection-1", "name": "Policies"}],
        ),
    ],
)
async def test_catalog_uses_gateway_and_user_bearer(
    monkeypatch, resource_type, path, payload, expected
):
    def respond(request):
        assert str(request.url) == f"https://gateway.example{path}"
        assert request.headers["Authorization"] == "Bearer caller-token"
        assert "x-internal-service-token" not in request.headers
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    assert (
        await ResourceCatalogClient("https://gateway.example").list_resources(
            resource_type, "caller-token"
        )
        == expected
    )


@pytest.mark.parametrize("status,error", [(401, UnauthorizedError), (403, ForbiddenError)])
async def test_catalog_denial_is_not_an_empty_success(monkeypatch, status, error):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(error):
        await ResourceCatalogClient("https://gateway.example").list_resources("agent", "jwt")
