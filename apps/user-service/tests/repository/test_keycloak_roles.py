import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import DependencyUnavailableError
import pytest

from src.repository.user_role_repository import UserRoleRepository


def test_manageable_excludes_basic_role_but_allows_custom_roles():
    from src.repository.keycloak_role_client import manageable

    assert not manageable("basic")
    assert manageable("custom-manager")


@pytest.mark.asyncio
async def test_user_roles_include_effective_inherited_assignments():
    repo = UserRoleRepository()

    async def request(method, path, **kwargs):
        if path.endswith("/realm/composite"):
            return [{"id": "r1", "name": "custom-manager"}, {"id": "r2", "name": "offline_access"}]
        if path.endswith("/realm"):
            return []
        return {"attributes": {"agentic.primary_role": ["custom-manager"]}}

    repo.client = SimpleNamespace(request=request)
    assert await repo.list_user_roles(uuid.uuid4()) == [
        {"id": "r1", "name": "custom-manager", "is_primary": True, "inherited": True}
    ]


@pytest.mark.asyncio
async def test_keycloak_transport_propagates_failure(monkeypatch):
    import httpx

    from src.repository.keycloak_role_client import KeycloakRoleClient

    response = httpx.Response(503, request=httpx.Request("GET", "https://kc/roles"))
    monkeypatch.setattr(
        "src.service.keycloak_service.get_keycloak_service",
        lambda: SimpleNamespace(_keycloak_request=AsyncMock(return_value=response)),
    )
    with pytest.raises(DependencyUnavailableError):
        await KeycloakRoleClient().request("GET", "/roles", missing=True)


@pytest.mark.asyncio
async def test_role_replacement_preserves_infrastructure_and_validates_before_mutation():
    repo = UserRoleRepository()
    calls = []

    async def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/roles/enduser":
            return {"id": "new", "name": "enduser"}
        if path.endswith("/realm") and method == "GET":
            return [
                {"id": "old", "name": "custom-admin"},
                {"id": "default", "name": "offline_access"},
            ]
        if method == "GET":
            return {"attributes": {"unrelated": ["retained"]}}

    repo.client = SimpleNamespace(request=request)
    assert await repo.replace_roles("subject", ["enduser"], "enduser") == 1
    deleted = next(kwargs["json"] for method, path, kwargs in calls if method == "DELETE")
    assert deleted == [{"id": "old", "name": "custom-admin"}]
    updated = next(kwargs["json"] for method, path, kwargs in calls if method == "PUT")
    assert updated["attributes"] == {"unrelated": ["retained"], "agentic.primary_role": ["enduser"]}


@pytest.mark.asyncio
async def test_profile_metadata_is_admin_editable_only():
    from src.repository.keycloak_role_client import ensure_identity_user_profile

    client = SimpleNamespace(
        request=AsyncMock(side_effect=[{"attributes": [{"name": "email"}]}, None])
    )
    await ensure_identity_user_profile(client)
    profile = client.request.call_args.kwargs["json"]
    protected = [
        a for a in profile["attributes"] if a["name"].startswith(("agentic.", "agenticai."))
    ]
    assert len(protected) == 8
    assert any(a["name"] == "agentic.legacy_identity_id" for a in protected)
    assert all(a["permissions"]["edit"] == ["admin"] for a in protected)


@pytest.mark.asyncio
async def test_permissions_are_discovered_from_client_role_grants():
    from src.repository.keycloak_role_client import CoarseRoleRecord
    from src.repository.permission_repository import PermissionRepository

    repo = PermissionRepository()
    repo.client = SimpleNamespace(clients=AsyncMock(return_value=[]))
    repo.role_repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                CoarseRoleRecord(
                    "r1",
                    "agent-workspace-admin",
                    None,
                    "agent-service",
                    ("agent:read", "agent:create", "*"),
                ),
                CoarseRoleRecord("r2", "agent-viewer", None, "agent-service", ("agent:read",)),
                CoarseRoleRecord("r3", "empty", None, "rag-service", ()),
            ]
        )
    )
    permissions = await repo.get_all()
    assert [(p.name, p.service, p.entity, p.action, p.feature) for p in permissions] == [
        ("agent:create", "agent-service", "agent", "create", "agents"),
        ("agent:read", "agent-service", "agent", "read", "agents"),
    ]


@pytest.mark.asyncio
async def test_view_permissions_are_discovered_without_local_api_definitions():
    from src.repository.keycloak_role_client import CoarseRoleRecord
    from src.repository.permission_repository import PermissionRepository

    repo = PermissionRepository()
    repo.client = SimpleNamespace(clients=AsyncMock(return_value=[]))
    repo.role_repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                CoarseRoleRecord(
                    "r1", "custom-bundle", None, "user-service-client", ("custom_page:view",)
                ),
            ]
        )
    )
    permissions = await repo.get_all()
    assert [(p.name, p.action, p.service) for p in permissions] == [
        ("custom_page:view", "view", "user-service")
    ]


@pytest.mark.asyncio
async def test_datasource_view_catalog_belongs_to_rag_knowledge_bundle():
    from src.repository.keycloak_role_client import CoarseRoleRecord
    from src.repository.permission_repository import PermissionRepository

    repo = PermissionRepository()
    repo.client = SimpleNamespace(clients=AsyncMock(return_value=[]))
    repo.role_repo = SimpleNamespace(get_all=AsyncMock(return_value=[
        CoarseRoleRecord(
            "knowledge-manager-id", "knowledge-manager", None,
            "rag-service-client", ("datasource:read", "datasource:view"),
        ),
    ]))
    permission = next(p for p in await repo.get_all() if p.name == "datasource:view")
    assert (permission.service, permission.feature, permission.label) == (
        "rag-service", "knowledge", "View Datasources",
    )


@pytest.mark.asyncio
async def test_cross_service_grant_keeps_permission_owner_and_feature():
    from src.repository.keycloak_role_client import CoarseRoleRecord
    from src.repository.permission_repository import PermissionRepository

    repo = PermissionRepository()
    repo.client = SimpleNamespace(clients=AsyncMock(return_value=[]))
    repo.role_repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                CoarseRoleRecord("r1", "mixed-bundle", None, "rag-service", ("agent:read",)),
            ]
        )
    )
    permission = (await repo.get_all())[0]
    assert (permission.service, permission.feature) == ("agent-service", "agents")


@pytest.mark.asyncio
async def test_catalog_includes_unassigned_provider_scopes_from_owning_client():
    from src.repository.keycloak_role_client import CoarseRoleRecord, catalog_cache
    from src.repository.permission_repository import PermissionRepository

    catalog_cache.clear()
    repo = PermissionRepository()
    repo.role_repo = SimpleNamespace(get_all=AsyncMock(return_value=[
        CoarseRoleRecord("reader", "agent-workspace-user", None,
                         "agent-service-client", ("provider:read",)),
    ]))
    request = AsyncMock(return_value=[
        {"name": "provider", "type": "agentic:feature",
         "scopes": [{"name": action} for action in ("read", "create", "update", "delete")]},
        {"name": "agent:private-id", "type": "agentic:instance",
         "scopes": [{"name": "read"}]},
    ])
    repo.client = SimpleNamespace(
        clients=AsyncMock(return_value=[{"id": "agent-client", "clientId": "agent-service-client"}]),
        request=request,
    )
    try:
        permissions = await repo.get_all()
        assert {p.name for p in permissions} == {
            "provider:read", "provider:create", "provider:update", "provider:delete",
        }
        assert len(permissions) == 4
        assert all(p.service == "agent-service" for p in permissions)
        assert await repo.get_all(service="tools-service") == []
        assert len(await repo.get_all(entity="provider")) == 4
        request.assert_awaited_once_with(
            "GET", "/clients/agent-client/authz/resource-server/resource", params={"max": -1}
        )
    finally:
        catalog_cache.clear()


@pytest.mark.asyncio
async def test_composite_expansion_is_recursive_and_cycle_safe():
    from src.repository.keycloak_role_client import KeycloakRoleClient

    client = KeycloakRoleClient()
    roles = {
        "a": {"id": "a", "name": "custom", "composite": True},
        "b": {
            "id": "b",
            "name": "bundle",
            "composite": True,
            "attributes": {"agentic.permissions": ["read"]},
        },
    }

    async def request(method, path):
        parts = path.split("/")
        if path.endswith("/composites"):
            return [roles["b" if parts[2] == "a" else "a"]]
        return roles[parts[2]]

    client.request = request
    assert await client.expanded_permissions({"id": "a"}) == ["read"]


@pytest.mark.asyncio
async def test_cutover_dry_run_fills_missing_metadata_and_refuses_changed_grants():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    role = {"id": "r", "name": "manager", "attributes": {"unrelated": ["keep"]}}

    async def request(method, path, **kwargs):
        if path == "/roles/manager":
            return role
        if path.endswith("/composites"):
            return []
        return None

    client = SimpleNamespace(request=AsyncMock(side_effect=request))
    snapshot = {
        "composite_roles": [{"name": "manager"}],
        "role_permissions": [{"role_name": "manager", "permission_name": "user:read"}],
    }
    assert await reconcile_role_metadata(client, snapshot, apply=False) == 1
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
    role["attributes"]["agentic.permissions"] = ["user:delete"]
    with pytest.raises(ValueError, match="conflict"):
        await reconcile_role_metadata(client, snapshot, apply=True)


@pytest.mark.asyncio
async def test_direct_service_client_roles_are_resolved_without_realm_roles():
    from src.service.permission_resolver_service import PermissionResolverService

    resolver = PermissionResolverService(cache_ttl_seconds=0)
    resolver.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(return_value=[]),
        effective_client_permissions=AsyncMock(return_value=["agent:read"]),
    )
    assert await resolver.resolve_effective_access(uuid.uuid4()) == (["agent:read"], False)


@pytest.mark.asyncio
async def test_service_client_discovery_uses_configured_ids(monkeypatch):
    from src.repository import keycloak_role_client

    monkeypatch.setattr(
        keycloak_role_client,
        "env",
        SimpleNamespace(
            KEYCLOAK_AGENT_SERVICE_CLIENT_ID="custom-agent",
            KEYCLOAK_RAG_SERVICE_CLIENT_ID="custom-rag",
            KEYCLOAK_TOOLS_SERVICE_CLIENT_ID="custom-tools",
            KEYCLOAK_USER_SERVICE_CLIENT_ID="custom-user",
        ),
        raising=False,
    )

    class Client(keycloak_role_client.KeycloakRoleClient):
        async def pages(self, path, **params):
            assert path == "/clients"
            return [{"clientId": "custom-agent"}, {"clientId": "web-client"},
                    {"clientId": "agent-service-client"}]

    keycloak_role_client.catalog_cache.clear()
    assert [item["clientId"] for item in await Client().clients()] == ["custom-agent"]
    keycloak_role_client.catalog_cache.clear()


@pytest.mark.asyncio
async def test_feature_role_grant_change_invalidates_cached_access(monkeypatch):
    import src.service.permission_resolver_service as resolver_module
    from src.service.coarse_role_service import RoleService

    resolver = resolver_module.PermissionResolverService()
    resolver._cache[uuid.uuid4()] = (float("inf"), ["*"], True)
    monkeypatch.setattr(resolver_module, "_permission_resolver_service_instance", resolver)
    service = RoleService()
    role = SimpleNamespace(id="role", name="feature", permissions=[], service_client="user-service")
    service.repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=role), update=AsyncMock(return_value=role)
    )
    service.permission_repo = SimpleNamespace(get_all=AsyncMock(return_value=[]))
    await service.set_role_permissions("feature", [])
    assert resolver._cache == {}


@pytest.mark.asyncio
async def test_cutover_empty_descriptions_are_idempotent():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {
                    "id": "r",
                    "name": "manager",
                    "description": "",
                    "attributes": {"agentic.permissions": []},
                },
                [],
            ]
        )
    )
    assert (
        await reconcile_role_metadata(
            client, {"composite_roles": [{"name": "manager", "description": None}]}, apply=False
        )
        == 0
    )


@pytest.mark.asyncio
async def test_cutover_primary_metadata_uses_explicit_user_map_and_effective_assignments():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {"id": "kc-user", "attributes": {"unrelated": ["keep"]}},
                [{"id": "role", "name": "auditor"}],
                None,
            ]
        )
    )
    snapshot = {
        "users": [{"id": "legacy-user", "role": "enduser"}],
        "user_roles": [{"user_id": "legacy-user", "role_name": "auditor", "is_primary": True}],
    }
    count = await reconcile_role_metadata(
        client, snapshot, mappings={"users": {"legacy-user": "kc-user"}}, apply=True
    )
    assert count == 1
    assert client.request.call_args.args == ("PUT", "/users/kc-user")
    assert client.request.call_args.kwargs["json"]["attributes"] == {
        "unrelated": ["keep"],
        "agentic.primary_role": ["auditor"],
    }


@pytest.mark.asyncio
async def test_cutover_primary_role_never_adds_missing_grants():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    client = SimpleNamespace(request=AsyncMock(side_effect=[{"attributes": {}}, []]))
    with pytest.raises(ValueError, match="assigned"):
        await reconcile_role_metadata(
            client,
            {"users": [{"id": "old", "role": "system-admin"}]},
            mappings={"users": {"old": "kc"}},
            apply=True,
        )
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


def test_primary_role_fallback_matches_user_profile_priority():
    from src.repository.keycloak_role_client import primary_role_name

    assert primary_role_name(["auditor", "system-admin"], []) == "system-admin"
    assert primary_role_name(["auditor", "system-admin"], ["auditor"]) == "auditor"
    assert primary_role_name(["auditor", "enduser"], ["missing"]) == "enduser"


@pytest.mark.asyncio
async def test_cutover_preserves_existing_primary_metadata_and_refuses_conflict():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    snapshot = {"users": [{"id": "old", "role": "auditor"}]}
    client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {"attributes": {"agentic.primary_role": ["auditor"]}},
                [{"name": "auditor"}],
            ]
        )
    )
    assert (
        await reconcile_role_metadata(
            client, snapshot, mappings={"users": {"old": "kc"}}, apply=True
        )
        == 0
    )
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
    client.request = AsyncMock(
        side_effect=[{"attributes": {"agentic.primary_role": ["enduser"]}}, [{"name": "auditor"}]]
    )
    with pytest.raises(ValueError, match="conflict"):
        await reconcile_role_metadata(
            client, snapshot, mappings={"users": {"old": "kc"}}, apply=True
        )


@pytest.mark.asyncio
async def test_missing_empty_permission_attribute_is_already_reconciled():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[{"id": "r", "name": "member", "attributes": {}, "description": ""}, []]
        )
    )
    assert (
        await reconcile_role_metadata(
            client, {"composite_roles": [{"name": "member"}]}, apply=False
        )
        == 0
    )


@pytest.mark.asyncio
async def test_existing_nonempty_permissions_conflict_with_empty_source():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    client = SimpleNamespace(
        request=AsyncMock(
            return_value={
                "id": "r",
                "name": "member",
                "attributes": {"agentic.permissions": ["user:read"]},
            }
        )
    )
    with pytest.raises(ValueError, match="conflict"):
        await reconcile_role_metadata(client, {"composite_roles": [{"name": "member"}]}, apply=True)
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
