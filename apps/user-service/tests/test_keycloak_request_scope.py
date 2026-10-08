"""Directory operations reuse HTTP connections only for their async scope."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.repository.user_repository import UserRepository
from src.service.keycloak_service import KeycloakService


@pytest.fixture
def pooled_client(monkeypatch):
    clients = []
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        client = real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
        )
        clients.append(client)
        return client

    monkeypatch.setattr("src.service.keycloak_service.httpx.AsyncClient", factory)
    service = KeycloakService()
    service._get_admin_token = AsyncMock(return_value="test-token")
    monkeypatch.setattr(service, "get_base_url", lambda: "https://kc.invalid")
    monkeypatch.setattr(service, "get_realm", lambda: "runtime-realm")
    return service, clients


async def test_nested_scope_reuses_client_including_child_tasks_and_closes(pooled_client):
    service, clients = pooled_client
    async with service.admin_request_scope():
        await service._keycloak_request("GET", "/users")
        async with service.admin_request_scope():
            await asyncio.gather(*(service._keycloak_request("GET", "/roles") for _ in range(3)))
        assert len(clients) == 1 and not clients[0].is_closed
    assert clients[0].is_closed
    await service._keycloak_request("GET", "/users")
    assert len(clients) == 2 and not clients[1].is_closed


async def test_scope_closes_and_resets_after_error(pooled_client):
    service, clients = pooled_client
    with pytest.raises(ValueError, match="failed"):
        async with service.admin_request_scope():
            await service._keycloak_request("GET", "/users")
            raise ValueError("failed")
    assert clients[0].is_closed
    async with service.admin_request_scope():
        assert len(clients) == 2 and not clients[1].is_closed
    assert clients[1].is_closed


async def test_independent_operations_have_separate_scopes(pooled_client):
    service, clients = pooled_client
    arrived = asyncio.Event()
    count = 0

    async def operation():
        nonlocal count
        async with service.admin_request_scope():
            count += 1
            if count == 2:
                arrived.set()
            await arrived.wait()
            assert len(clients) == 2
            await service._keycloak_request("GET", "/users")

    await asyncio.gather(operation(), operation())
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("list_paginated", {"include_external_keycloak_users": False}),
        ("count_by_role", {}),
        ("list_assignable", {"organization_id": "missing", "root_ids": []}),
        ("get_all", {}),
    ],
)
async def test_directory_operations_open_and_close_scope(pooled_client, method, kwargs):
    service, clients = pooled_client
    repo = UserRepository(keycloak=service)
    repo._role_index = AsyncMock(return_value={})
    request = service._keycloak_request

    async def scoped_request(*args, **options):
        assert len(clients) == 1 and not clients[0].is_closed
        return await request(*args, **options)

    service._keycloak_request = scoped_request
    await getattr(repo, method)(**kwargs)
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.parametrize("method", ["get_by_id", "get_by_ids", "get_by_email"])
async def test_bounded_lookup_reuses_profile_roles_and_group_page_connections(
    pooled_client, method
):
    service, clients = pooled_client
    subject = uuid.uuid4()
    original = service._keycloak_request

    async def request(verb, path, **kwargs):
        response = await original(verb, path, **kwargs)
        profile = {"id": str(subject), "email": "person@example.test", "username": "person"}
        if path.endswith("/composite"):
            data = [{"name": "reader"}]
        elif path.endswith("/groups"):
            data = [{"path": "/Team"}] * 100 if kwargs["params"]["first"] == 0 else []
        else:
            data = [profile] if path == "/users" else profile
        return httpx.Response(200, json=data, request=response.request)

    service._keycloak_request = request
    argument = {
        "get_by_id": subject,
        "get_by_ids": [subject, uuid.uuid4()],
        "get_by_email": "person@example.test",
    }[method]
    result = await getattr(UserRepository(service), method)(argument)
    assert result
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.parametrize("through_user_service", [False, True])
async def test_cold_permission_resolution_reuses_one_connection_scope(
    pooled_client, through_user_service
):
    from src.service.permission_resolver_service import PermissionResolverService
    from src.service.user_service import UserService

    service, clients = pooled_client
    subject = uuid.uuid4()
    resolver = PermissionResolverService()
    resolver.user_repo = UserRepository(service)

    async def assignments(user_id):
        await service._keycloak_request("GET", f"/users/{user_id}/role-mappings/realm")
        return [{"name": "reader"}]

    async def client_permissions(user_id):
        await service._keycloak_request("GET", "/clients")
        return ["agent:list"]

    async def role_permissions(names):
        await service._keycloak_request("GET", "/roles")
        return {"reader": []}

    resolver.user_role_repo = SimpleNamespace(
        list_user_roles=assignments, effective_client_permissions=client_permissions
    )
    resolver.role_repo = SimpleNamespace(get_access_by_names=role_permissions)
    if through_user_service:
        app = UserService()
        app.keycloak = service
        app.permission_resolver = resolver

        async def profile(user_id):
            await service._keycloak_request("GET", f"/users/{user_id}")
            return SimpleNamespace(id=user_id)

        app.user_repo = SimpleNamespace(get_by_id=profile)
        assert await app.get_user_permissions(subject) == {
            "permissions": ["agent:list"],
            "is_admin": False,
        }
    else:
        assert await resolver.resolve_effective_access(subject) == (["agent:list"], False)
    assert len(clients) == 1 and clients[0].is_closed
    assert await resolver.resolve_effective_access(subject) == (["agent:list"], False)
    assert len(clients) == 1
