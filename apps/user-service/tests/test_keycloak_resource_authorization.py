"""Keycloak Authorization Services projection for instance permissions."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from config_manager import env
from error_contract import ApplicationError
import httpx
import pytest

from src.main import reconcile_resource_authorization_startup
from src.repository.keycloak_resource_authorization import (
    ResourceAuthorizationProjectionRepository,
    instance_authorization_objects,
)


def test_resource_clients_use_configured_ids(monkeypatch):
    from src.repository import keycloak_resource_authorization

    monkeypatch.setattr(
        keycloak_resource_authorization,
        "env",
        SimpleNamespace(
            KEYCLOAK_AGENT_SERVICE_CLIENT_ID="custom-agent",
            KEYCLOAK_RAG_SERVICE_CLIENT_ID="custom-rag",
        ),
    )
    assert keycloak_resource_authorization.resource_clients() == {
        "agent": "custom-agent",
        "rag_collection": "custom-rag",
    }


def test_instance_authorization_expands_levels_and_uses_exact_subject_ids() -> None:
    objects = instance_authorization_objects(
        [
            {
                "resource_type": "agent",
                "resource_id": "agent-1",
                "user_id": "user-1",
                "organization_id": None,
                "permission_level": "read",
            },
            {
                "resource_type": "agent",
                "resource_id": "agent-1",
                "user_id": None,
                "organization_id": "group-1",
                "permission_level": "write",
            },
        ],
        "agent",
    )

    assert objects["resources"] == [
        {
            "name": "agent:agent-1",
            "type": "agentic:instance",
            "ownerManagedAccess": False,
            "scopes": [
                {"name": "admin"},
                {"name": "execute"},
                {"name": "owner"},
                {"name": "read"},
                {"name": "write"},
            ],
        }
    ]
    user = next(policy for policy in objects["policies"] if policy["type"] == "user")
    group = next(policy for policy in objects["policies"] if policy["type"] == "group")
    assert user["users"] == ["user-1"]
    assert group["groups"] == [{"id": "group-1", "extendChildren": False}]
    read_permission = next(
        permission for permission in objects["permissions"] if permission["name"].endswith("#read")
    )
    assert read_permission["policies"] == [
        "agentic:instance:group:group-1",
        "agentic:instance:user:user-1",
    ]
    write_permission = next(
        permission for permission in objects["permissions"] if permission["name"].endswith("#write")
    )
    assert write_permission["policies"] == ["agentic:instance:group:group-1"]


@pytest.mark.asyncio
async def test_mutation_clears_before_sql_and_reconciles_afterward() -> None:
    events: list[str] = []
    projection = ResourceAuthorizationProjectionRepository(
        organization_repo=MagicMock(), client=MagicMock(), redis=MagicMock()
    )

    @asynccontextmanager
    async def locked():
        events.append("lock")
        yield

    projection._lock = locked
    projection.clear = AsyncMock(side_effect=lambda: events.append("clear"))
    projection.reconcile_all = AsyncMock(side_effect=lambda: events.append("reconcile"))

    async def mutate() -> str:
        events.append("sql")
        return "saved"

    assert await projection.project_mutation(mutate) == "saved"
    assert events == ["lock", "clear", "sql", "reconcile"]


@pytest.mark.asyncio
async def test_failed_revocation_never_reinstalls_stale_grants() -> None:
    projection = ResourceAuthorizationProjectionRepository(
        organization_repo=MagicMock(), client=MagicMock(), redis=MagicMock()
    )

    @asynccontextmanager
    async def locked():
        yield

    projection._lock = locked
    projection.clear = AsyncMock()
    projection.reconcile_all = AsyncMock()

    async def failed_delete() -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await projection.project_mutation(failed_delete)

    projection.clear.assert_awaited_once()
    projection.reconcile_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_reconciliation_failure_is_not_suppressed() -> None:
    projection = MagicMock()
    projection.reconcile_startup = AsyncMock(side_effect=RuntimeError("Keycloak unavailable"))

    with pytest.raises(RuntimeError, match="Keycloak unavailable"):
        await reconcile_resource_authorization_startup(projection)


@pytest.mark.asyncio
async def test_reconcile_writes_instance_objects_to_owning_service_client() -> None:
    client = MagicMock()
    client.clients = AsyncMock(
        return_value=[
            {"id": "agent-client", "clientId": env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID},
            {"id": "rag-client", "clientId": env.KEYCLOAK_RAG_SERVICE_CLIENT_ID},
        ]
    )

    async def request(method, path, **_kwargs):
        if method == "GET" and path.endswith("/resource"):
            return [
                {
                    "_id": "resource-uuid",
                    "name": "agent:agent-1",
                    "type": "agentic:instance",
                }
            ]
        if method == "GET" and path.endswith("/policy"):
            return [{"id": "policy-uuid", "name": "agentic:instance:user:user-1"}]
        return None

    client.request = AsyncMock(side_effect=request)
    projection = ResourceAuthorizationProjectionRepository(client=client, redis=MagicMock())
    projection.inventory = AsyncMock(
        return_value=[
            {
                "resource_type": "agent",
                "resource_id": "agent-1",
                "user_id": "user-1",
                "organization_id": None,
                "permission_level": "read",
            }
        ]
    )

    await projection.reconcile_all()

    paths = [call.args[1] for call in client.request.await_args_list]
    assert "/clients/agent-client/authz/resource-server/resource" in paths
    assert "/clients/agent-client/authz/resource-server/policy/user" in paths
    assert "/clients/agent-client/authz/resource-server/permission/scope" in paths
    assert not any(
        call.args[0] == "POST" and "rag-client" in call.args[1]
        for call in client.request.await_args_list
    )
    permission_call = next(
        call
        for call in client.request.await_args_list
        if call.args[1].endswith("/permission/scope")
    )
    assert permission_call.kwargs["json"]["resources"] == ["resource-uuid"]
    assert permission_call.kwargs["json"]["policies"] == ["policy-uuid"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scoped", [False, True])
async def test_inventory_reads_direct_assignments_without_identity_serialization(scoped) -> None:
    row = SimpleNamespace(
        resource_type="agent",
        resource_id="agent-1",
        organization_id=None,
        user_id="user-1",
        permission_level="read",
    )
    result = MagicMock()
    result.scalars.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def session_context():
        yield session

    organizations = MagicMock()
    organizations.get_by_id = AsyncMock(return_value={"is_active": True})
    projection = ResourceAuthorizationProjectionRepository(
        organization_repo=organizations, client=MagicMock()
    )
    projection.client.request = AsyncMock(return_value={"id": "user-1"})
    projection._session = session_context

    inventory = (
        await projection.inventory("agent", {"agent-1"}) if scoped else await projection.inventory()
    )
    if scoped:
        query = str(
            session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert "resource_type = 'agent'" in query
        assert "resource_id IN ('agent-1')" in query
        # All subjects sharing the resource must survive a target's save.
        assert "organization_id =" not in query and "user_id =" not in query
    assert inventory == [
        {
            "resource_type": "agent",
            "resource_id": "agent-1",
            "organization_id": None,
            "user_id": "user-1",
            "permission_level": "read",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("scoped", [False, True])
async def test_inventory_excludes_inactive_organization_grants(scoped) -> None:
    row = SimpleNamespace(
        resource_type="agent",
        resource_id="agent-1",
        organization_id="group-1",
        user_id=None,
        permission_level="read",
    )
    result = MagicMock()
    result.scalars.return_value = [row]
    session = MagicMock(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def session_context():
        yield session

    organizations = MagicMock()
    organizations.get_by_id = AsyncMock(return_value={"is_active": False})
    projection = ResourceAuthorizationProjectionRepository(
        organization_repo=organizations, client=MagicMock()
    )
    projection._session = session_context

    inventory = (
        await projection.inventory("agent", {"agent-1"}) if scoped else await projection.inventory()
    )
    assert inventory == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("lookup", [None, {"id": "user-1", "enabled": False}, RuntimeError("unavailable")])
async def test_inventory_validates_unique_user_subjects(scoped, lookup):
    rows = [
        SimpleNamespace(resource_type="agent", resource_id=resource, user_id="user-1",
                        organization_id=None, permission_level="read")
        for resource in ["agent-1", "agent-2"]
    ]
    result = MagicMock()
    result.scalars.return_value = rows
    session = MagicMock(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def session_context():
        yield session

    request = AsyncMock(side_effect=lookup) if isinstance(lookup, Exception) else AsyncMock(return_value=lookup)
    projection = ResourceAuthorizationProjectionRepository(client=SimpleNamespace(request=request))
    projection._session = session_context
    if isinstance(lookup, Exception):
        with pytest.raises(RuntimeError, match="unavailable"):
            await projection.inventory()
    else:
        inventory = await projection.inventory("agent", {"agent-1", "agent-2"}) if scoped else await projection.inventory()
        assert len(inventory) == (0 if lookup is None else 2)
    request.assert_awaited_once_with("GET", "/users/user-1", missing=True)
    assert session.execute.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scoped", [False, True])
async def test_inventory_preserves_valid_grants_when_another_user_is_missing(scoped):
    rows = [
        SimpleNamespace(
            resource_type="agent",
            resource_id="agent-1",
            user_id=user_id,
            organization_id=organization_id,
            permission_level="read",
        )
        for user_id, organization_id in [
            ("missing-user", None), ("existing/user", None), (None, "group-1")
        ]
    ]
    result = MagicMock()
    result.scalars.return_value = rows
    session = MagicMock(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def session_context():
        yield session

    async def lookup(method, path, *, missing):
        assert method == "GET" and missing is True
        return {"id": "existing/user"} if path == "/users/existing%2Fuser" else None

    organizations = MagicMock(get_by_id=AsyncMock(return_value={"is_active": True}))
    projection = ResourceAuthorizationProjectionRepository(
        organization_repo=organizations,
        client=SimpleNamespace(request=AsyncMock(side_effect=lookup)),
    )
    projection._session = session_context
    inventory = (
        await projection.inventory("agent", {"agent-1"}) if scoped else await projection.inventory()
    )
    assert [row["user_id"] for row in inventory] == ["existing/user", None]
    assert projection.client.request.await_count == 2


@pytest.mark.asyncio
async def test_clear_preserves_feature_and_unmanaged_authorization_objects() -> None:
    client = MagicMock()
    client.clients = AsyncMock(
        return_value=[
            {"id": "agent-client", "clientId": env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID},
            {"id": "user-client", "clientId": env.KEYCLOAK_USER_SERVICE_CLIENT_ID},
        ]
    )

    async def request(method, path, **_kwargs):
        if method == "GET" and path.endswith("/policy"):
            return [
                {"id": "instance-policy", "name": "agentic:instance:user:user-1"},
                {"id": "feature-policy", "name": "agentic:permission:chat#read"},
            ]
        if method == "GET" and path.endswith("/resource"):
            return [
                {"_id": "instance-resource", "type": "agentic:instance"},
                {"_id": "feature-resource", "type": "agentic:feature"},
            ]
        return None

    client.request = AsyncMock(side_effect=request)
    projection = ResourceAuthorizationProjectionRepository(client=client, redis=MagicMock())

    await projection.clear()

    deleted = [call.args[1] for call in client.request.await_args_list if call.args[0] == "DELETE"]
    assert deleted == [
        "/clients/agent-client/authz/resource-server/policy/instance-policy",
        "/clients/agent-client/authz/resource-server/resource/instance-resource",
    ]
    assert not any("user-client" in call.args[1] for call in client.request.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_status", [404, 403, 503])
async def test_clear_tolerates_only_already_deleted_objects(monkeypatch, delete_status):
    from src.repository.keycloak_role_client import KeycloakRoleClient
    from src.service import keycloak_service

    client = KeycloakRoleClient()
    client.clients = AsyncMock(return_value=[
        {"id": "agent-client", "clientId": env.KEYCLOAK_AGENT_SERVICE_CLIENT_ID}
    ])
    deleted = []

    async def request(method, path, **kwargs):
        http_request = httpx.Request(method, f"https://keycloak.test{path}")
        if method == "DELETE":
            deleted.append(path)
            return httpx.Response(delete_status, request=http_request)
        payload = (
            [{"id": "cascaded-policy", "name": "agentic:instance:user:user-1"}]
            if path.endswith("/policy")
            else [{"_id": "removed-resource", "type": "agentic:instance"}]
        )
        return httpx.Response(200, json=payload, request=http_request)

    monkeypatch.setattr(
        keycloak_service, "get_keycloak_service",
        lambda: SimpleNamespace(_keycloak_request=request),
    )
    projection = ResourceAuthorizationProjectionRepository(client=client, redis=MagicMock())
    if delete_status == 404:
        await projection.clear()
        assert len(deleted) == 2
    else:
        with pytest.raises(ApplicationError):
            await projection.clear()
        assert len(deleted) == 1
