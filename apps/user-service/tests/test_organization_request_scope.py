"""Organization reads reuse a request-scoped Keycloak admin connection."""

import uuid
from types import SimpleNamespace

import httpx
from error_contract import register_error_handlers
import pytest
from fastapi import FastAPI

from src.api import dependencies
from src.api.routes import organizations_route, user_organizations_route
from src.service.keycloak_service import _ADMIN_REQUEST_CLIENT, get_keycloak_service


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["users", "children"])
async def test_organization_request_reuses_client_through_permission_and_controller(
    monkeypatch, resource
):
    actor = uuid.uuid4()
    organization = uuid.uuid4()
    clients = []
    current_client = None
    user_exists = True

    async def get_user(user_id):
        nonlocal current_client
        context = _ADMIN_REQUEST_CLIENT.get()
        assert context is not None, "Permission check must run inside the request client scope"
        current_client = context[1]
        assert not current_client.is_closed
        clients.append(current_client)
        return SimpleNamespace(id=actor) if user_exists else None

    async def permissions(user_id):
        assert user_id == actor
        assert _ADMIN_REQUEST_CLIENT.get()[1] is current_client
        return ["org:read"]

    async def read(*args, **kwargs):
        assert args[0] == organization
        assert kwargs["actor_id"] == actor
        async with get_keycloak_service().admin_request_scope():
            assert _ADMIN_REQUEST_CLIENT.get()[1] is current_client
        return {resource: [], "count": 0}

    monkeypatch.setattr(
        dependencies, "env", SimpleNamespace(INTERNAL_SERVICE_TOKEN="gateway-proof")
    )
    # The permission dependency imports the repository inside its body.
    monkeypatch.setattr(
        "src.repository.UserRepository", lambda: SimpleNamespace(get_by_id=get_user, exists_by_id=get_user)
    )
    monkeypatch.setattr(
        dependencies,
        "get_permission_resolver_service",
        lambda: SimpleNamespace(resolve_effective_permissions=permissions),
    )
    monkeypatch.setattr(
        user_organizations_route,
        "get_user_organization_controller",
        lambda: SimpleNamespace(get_organization_users=read),
    )
    monkeypatch.setattr(
        organizations_route,
        "get_organization_controller",
        lambda: SimpleNamespace(get_organization_children=read),
    )
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
    app.include_router(organizations_route.router)
    app.include_router(user_organizations_route.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for _ in range(2):
            response = await client.get(
                f"/organizations/{organization}/{resource}",
                headers={"x-gateway-token": "gateway-proof", "x-gateway-user-id": str(actor)},
            )
            assert response.status_code == 200
            assert response.json()["data"] == {resource: [], "count": 0}
            assert current_client.is_closed
            assert _ADMIN_REQUEST_CLIENT.get() is None
        user_exists = False
        response = await client.get(
            f"/organizations/{organization}/{resource}",
            headers={"x-gateway-token": "gateway-proof", "x-gateway-user-id": str(actor)},
        )
        assert response.status_code == 401
        assert current_client.is_closed
        assert _ADMIN_REQUEST_CLIENT.get() is None
    assert len({id(client) for client in clients}) == 3
