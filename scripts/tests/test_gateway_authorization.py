import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "gateway_authorization", ROOT / "scripts/gateway_authorization.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_inventory_maps_permissions_and_fails_closed():
    rows = module.inventory(ROOT)
    assert {row["audience"] for row in rows} == {
        "agent-service-client", "rag-service-client", "tools-service-client",
        "user-service-client",
    }

    def matches(path, method):
        return [
            r for r in rows if method in r["methods"] and re.fullmatch(r["path"], path)
        ]

    assert matches("/user-service/api/v1/roles", "GET")[0]["permissions"] == [
        "role#list"
    ]
    assert matches("/rag-service/api/v1/retrieval", "POST")[0]["permissions"] == [
        "document#search"
    ]
    assert matches("/agent-service/api/v1/agent-definitions", "POST")[0][
        "permissions"
    ] == ["agent#create"]
    assert not matches("/user-service/api/v1/unknown", "GET")
    assert not matches("/user-service/api/v1/internal/users/foo", "GET")
    assert not matches("/user-service/api/v1/roles/extra/unexpected", "GET")
    assert len(rows) > 250


def test_memory_index_routes_are_internal_only():
    rows = module.inventory(ROOT)
    for method, suffix, permission in (
        ("POST", "/memory/search", "memory#search"),
        ("POST", "/memory/facts", "memory#write"),
        ("DELETE", "/memory/facts/sample", "memory#write"),
    ):
        public = "/rag-service/api/v1" + suffix
        internal = "/internal" + public
        assert not any(
            method in row["methods"] and re.fullmatch(row["path"], public)
            for row in rows
        )
        assert any(
            method in row["methods"]
            and re.fullmatch(row["path"], internal)
            and permission in row["permissions"]
            for row in rows
        )


def test_inventory_resolves_permission_aliases_and_internal_user_routes():
    rows = module.inventory(ROOT)
    internal = [
        row
        for row in rows
        if re.fullmatch(row["path"], "/internal/user-service/api/v1/permissions/check")
    ]
    assert internal and internal[0]["authenticated_only"]
    source = """
router = APIRouter(prefix="/flows", dependencies=[Depends(require_user)])
_require_write = require_permission("flow:update")
@router.put("/{id}")
async def update(id: str, user=Depends(_require_write)): pass
"""
    row = next(iter(module.route_rows(source, "agent-service")))
    assert row["permissions"] == ["flow#update"]
    assert not row.get("authenticated_only")


def test_resource_policy_expands_composites_and_wildcard():
    roles = [
        {"id": "admin", "name": "system-admin"},
        {
            "id": "child",
            "name": "reader",
            "attributes": {"agentic.permissions": ["role:list"]},
        },
        {"id": "parent", "name": "composite", "children": ["child"]},
        {
            "id": "client",
            "name": "feature",
            "clientRole": True,
            "attributes": {"agentic.permissions": ["role:manage"]},
        },
    ]
    policy = module.authorization_settings(["role#list", "role#manage"], roles)
    assert policy["policyEnforcementMode"] == "ENFORCING"
    assert all(p["name"] != "Default Policy" for p in policy["policies"])
    permission = next(
        p for p in policy["policies"] if p["name"] == "agentic:permission:role#list"
    )
    import json

    assert set(json.loads(permission["config"]["applyPolicies"])) == {
        "agentic:role:admin",
        "agentic:role:child",
        "agentic:role:parent",
    }
    assert len(policy["resources"]) == 1
    assert {s["name"] for s in policy["scopes"]} == {"list", "manage"}


def test_reconcile_removes_default_allow_and_stale_managed_permissions():
    import asyncio

    calls = []

    class Client:
        async def pages(self, path, **kwargs):
            if path == "/roles":
                return [
                    {
                        "id": "r",
                        "name": "reader",
                        "attributes": {"agentic.permissions": []},
                    }
                ]
            return []

        async def clients(self):
            return [{"id": "c", "clientId": "user-service-client"}]

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if method != "GET":
                return None
            if path == "/roles-by-id/r":
                return {"id": "r", "name": "reader", "attributes": {}}
            if path.endswith("/resource"):
                return [
                    {
                        "id": "resource",
                        "name": "role",
                        "type": "agentic:feature",
                        "scopes": [{"name": "list"}],
                        "uris": ["/user-service/api/v1/roles"],
                    }
                ]
            if path.endswith("/policy"):
                return [
                    {"id": "default", "name": "Default Policy", "type": "js"},
                    {
                        "id": "stale",
                        "name": "agentic:permission:role#list",
                        "type": "scope",
                    },
                    {"id": "instance", "name": "instance-grant", "type": "group"},
                ]
            return []

    asyncio.run(module.reconcile(Client()))
    deleted = [path for method, path, _ in calls if method == "DELETE"]
    assert any(path.endswith("/default") for path in deleted)
    assert any(path.endswith("/stale") for path in deleted)
    assert not any(path.endswith("/instance") for path in deleted)
    imported = next(options["json"] for method, path, options in calls
                    if method == "POST" and path.endswith("/import"))
    assert imported["resources"][0]["uris"] == ["/user-service/api/v1/roles"]


def test_reconcile_updates_existing_provider_scope_permission():
    import asyncio

    calls = []
    permission = {
        "id": "existing-permission",
        "name": "agentic:permission:provider#read",
        "type": "scope",
    }
    associated = ["agentic:role:admin"]

    class Client:
        async def clients(self):
            return [{"id": "agent", "clientId": "agent-service-client"}]

        async def pages(self, path, **kwargs):
            return [{"id": "reader"}] if path == "/roles" else []

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/roles-by-id/reader":
                return {
                    "id": "reader",
                    "name": "enduser",
                    "attributes": {"agentic.permissions": ["provider:read"]},
                }
            if method == "GET" and path.endswith("/resource"):
                return [{
                    "name": "provider", "type": "agentic:feature",
                    "scopes": [{"name": "read"}], "uris": ["/providers"],
                }]
            if method == "GET" and path.endswith("/policy"):
                return [permission, {"id": "custom", "name": "custom", "type": "scope"}]
            # Existing live scope permissions kept their old associations on import.
            if method == "PUT" and path.endswith("/permission/scope/existing-permission"):
                associated[:] = kwargs["json"]["policies"]
            return None

    asyncio.run(module.reconcile(Client()))

    assert associated == ["agentic:role:reader"]
    update = next(options["json"] for method, path, options in calls if method == "PUT")
    assert update["resources"] == ["provider"]
    assert update["scopes"] == ["read"]
    assert update["decisionStrategy"] == "AFFIRMATIVE"
    imported = next(options["json"] for method, path, options in calls if path.endswith("/import"))
    assert imported["resources"][0]["uris"] == ["/providers"]
    assert not any(method == "DELETE" for method, _, _ in calls)
    assert not any(path.endswith("/custom") for _, path, _ in calls)


def test_policy_lock_denies_write_when_busy():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    import pytest
    from error_contract import DependencyUnavailableError

    lock = SimpleNamespace(acquire=AsyncMock(return_value=False), release=AsyncMock())
    redis = SimpleNamespace(lock=Mock(return_value=lock))

    async def run():
        async with module._shared.policy_write_lock(redis, "realm"):
            pytest.fail("Must not enter protected mutation")

    with pytest.raises(DependencyUnavailableError):
        asyncio.run(run())
    assert redis.lock.call_args.kwargs["timeout"] is None
    lock.release.assert_not_called()


def test_role_write_clears_grants_before_mutation_and_reconciles(monkeypatch):
    import asyncio
    import sys
    import types
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    package = types.ModuleType("isolated_repository")
    package.__path__ = [str(ROOT / "apps/user-service/src/repository")]
    monkeypatch.setitem(sys.modules, "isolated_repository", package)
    import importlib

    keycloak_role_client = importlib.import_module(
        "isolated_repository.keycloak_role_client"
    )
    keycloak_authorization = importlib.import_module(
        "isolated_repository.keycloak_authorization"
    )

    events = []

    @asynccontextmanager
    async def locked(*args):
        events.append("lock")
        yield
        events.append("unlock")

    @asynccontextmanager
    async def redis(**kwargs):
        yield object()

    async def clear(client):
        events.append("clear")

    async def sync(client):
        events.append("sync")

    async def request(*args, **kwargs):
        events.append("write")
        return "ok"

    monkeypatch.setitem(sys.modules, "redis.asyncio", SimpleNamespace(Redis=redis))
    monkeypatch.setitem(
        sys.modules,
        "config_manager",
        SimpleNamespace(
            env=SimpleNamespace(
                REDIS_HOST="redis",
                REDIS_PORT=6379,
                REDIS_DB=0,
                REDIS_PASSWORD="",
                KEYCLOAK_REALM="realm",
            )
        ),
    )
    monkeypatch.setattr(keycloak_authorization, "policy_write_lock", locked)
    monkeypatch.setattr(keycloak_authorization, "clear_feature_grants", clear)
    monkeypatch.setattr(keycloak_authorization, "reconcile", sync)
    client = keycloak_role_client.KeycloakRoleClient()
    monkeypatch.setattr(client, "_request", request)
    assert asyncio.run(client.request("PUT", "/roles-by-id/role", json={})) == "ok"
    assert events == ["lock", "clear", "write", "sync", "unlock"]


def test_bootstrap_sets_gateway_audience_and_claims_for_login_and_services(monkeypatch):
    import asyncio
    import importlib
    from unittest.mock import AsyncMock

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    bootstrap = importlib.import_module("bootstrap_gateway_authorization")
    monkeypatch.setenv("GATEWAY_KEYCLOAK_CLIENT_SECRET", "test-only-secret")
    monkeypatch.setenv("GATEWAY_KEYCLOAK_CLIENT_ID", "gateway")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "web")
    monkeypatch.setenv("KEYCLOAK_USER_SERVICE_CLIENT_ID", "custom-user-service")
    calls = []

    class Client:
        async def clients(self):
            return [{"id": "service-id", "clientId": "custom-user-service"}]

        async def pages(self, path, **kwargs):
            return []

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if method == "GET" and path == "/clients":
                return (
                    [{"id": "web-id"}] if kwargs["params"]["clientId"] == "web" else []
                )
            return [] if method == "GET" else None

    sync = AsyncMock()
    monkeypatch.setattr(bootstrap, "reconcile", sync)
    asyncio.run(bootstrap.bootstrap(Client()))
    mappers = [
        (path, options["json"])
        for method, path, options in calls
        if method == "POST" and path.endswith("/protocol-mappers/models")
    ]
    audiences = [
        (path, mapper)
        for path, mapper in mappers
        if mapper["protocolMapper"] == "oidc-audience-mapper"
    ]
    assert [(path, mapper["config"]["included.client.audience"]) for path, mapper in audiences] == [
        ("/clients/web-id/protocol-mappers/models", "gateway"),
        ("/clients/service-id/protocol-mappers/models", "gateway"),
    ]
    groups = next(
        mapper for _, mapper in mappers if mapper["name"] == "agentic-gateway-groups"
    )
    assert groups["config"]["userinfo.token.claim"] == "true"
    sync.assert_awaited_once()


def test_bootstrap_limits_the_login_token_to_the_platform_realm_roles(monkeypatch):
    """The login client gets no full scope: only the platform roles the gateway reads
    (``realm_access.roles``) are mapped into its tokens, declaratively."""
    import asyncio
    import importlib
    from unittest.mock import AsyncMock

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    bootstrap = importlib.import_module("bootstrap_gateway_authorization")
    monkeypatch.setenv("GATEWAY_KEYCLOAK_CLIENT_SECRET", "test-only-secret")
    monkeypatch.setenv("GATEWAY_KEYCLOAK_CLIENT_ID", "gateway")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "web")
    login_client = {
        "id": "web-id",
        "clientId": "web",
        "publicClient": True,
        "fullScopeAllowed": True,
        "attributes": {"post.logout.redirect.uris": "+"},
    }
    realm_roles = [
        {"id": "r-admin", "name": "system-admin"},
        {"id": "r-enterprise", "name": "enterprise-admin"},
        {"id": "r-runtime", "name": "analyst", "composite": True},
        {"id": "r-default", "name": "default-roles-realm"},
    ]
    calls = []

    class Client:
        async def clients(self):
            return []

        async def pages(self, path, **kwargs):
            assert path == "/roles"
            return realm_roles

        async def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if method == "GET" and path == "/clients":
                return [login_client] if kwargs["params"]["clientId"] == "web" else []
            if method == "GET" and path == "/clients/web-id/scope-mappings/realm":
                return [
                    {"id": "r-admin", "name": "system-admin"},
                    {"id": "r-runtime", "name": "analyst", "composite": True},
                ]
            return [] if method == "GET" else None

    monkeypatch.setattr(bootstrap, "reconcile", AsyncMock())
    asyncio.run(bootstrap.bootstrap(Client()))

    (update,) = [
        options["json"] for method, path, options in calls
        if method == "PUT" and path == "/clients/web-id"
    ]
    assert update == {**login_client, "fullScopeAllowed": False}
    scope = [
        (method, options["json"]) for method, path, options in calls
        if path == "/clients/web-id/scope-mappings/realm" and method != "GET"
    ]
    # enduser does not exist in this realm and is skipped; a stale mapping goes away.
    assert scope == [
        ("POST", [{"id": "r-enterprise", "name": "enterprise-admin"}]),
        ("DELETE", [{"id": "r-runtime", "name": "analyst", "composite": True}]),
    ]


def test_bootstrap_client_discovery_uses_configured_ids(monkeypatch):
    import asyncio
    import importlib
    from unittest.mock import AsyncMock

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    bootstrap = importlib.import_module("bootstrap_gateway_authorization")
    monkeypatch.setenv("KEYCLOAK_BASE_URL", "https://keycloak.example")
    monkeypatch.setenv("KEYCLOAK_REALM", "custom-realm")
    for service in ("USER", "AGENT", "RAG", "TOOLS"):
        monkeypatch.setenv(f"KEYCLOAK_{service}_SERVICE_CLIENT_ID", f"custom-{service.lower()}")
    client = bootstrap.AdminClient()
    client.pages = AsyncMock(return_value=[
        {"clientId": "custom-user"}, {"clientId": "agent-service-client"},
    ])
    assert client.realm == "custom-realm"
    assert asyncio.run(client.clients()) == [{"clientId": "custom-user"}]


def test_inventory_keeps_registered_resource_prefixes_after_module_moves():
    rows = module.inventory(ROOT)

    def match(path, method):
        return [row for row in rows if method in row["methods"] and re.fullmatch(row["path"], path)]

    for path in ("/auth/me", "/auth/settings", "/auth/enterprise-settings", "/auth/health"):
        assert not match("/agent-service/api/v1" + path, "GET")
    preview = match("/agent-service/api/v1/ingest/source-preview", "POST")[0]
    assert preview["permissions"] == ["datasource#update"]
    assert not preview.get("authenticated_only")
    # Syncs run in-process: no ingest route is reachable on the internal path.
    assert not match("/agent-service/api/v1/ingest/batch", "POST")
    assert not match("/internal/agent-service/api/v1/ingest/source-preview", "POST")
    # Stored connector configurations are served to services only.
    configs = "/api/v1/internal/users/0b0e7a4e-1d7c-4f0e-9d3c-5a4f6f3b2a10/connector-configs"
    assert match("/internal/user-service" + configs, "POST")[0]["authenticated_only"]
    assert match("/internal/user-service" + configs + "/1", "GET")
    assert not match("/user-service" + configs, "POST")
    assert not match("/user-service" + configs + "/1", "GET")
    assert match("/agent-service/api/v1/chat/messages", "POST")[0]["permissions"] == ["chat#send"]
    assert match("/agent-service/api/v1/admin/providers/available-models", "GET")[0][
        "permissions"
    ] == ["provider#read"]
    assert not match("/agent-service/api/v1/chat/send-chat-message", "POST")
    assert not match("/agent-service/api/v1/batch", "POST")
    assert not match("/internal/agent-service/api/v1/chat/messages", "POST")


def test_checked_in_gateway_inventory_matches_current_routes():
    import json

    checked_in = json.loads((ROOT / "configs/apisix/gateway-policies.json").read_text())
    assert checked_in == module.inventory(ROOT)


def test_datasource_routes_use_their_own_service_client():
    rows = module.inventory(ROOT)
    datasource_rows = [
        row for row in rows
        if any(permission.startswith("datasource#") for permission in row["permissions"])
    ]
    assert {row["audience"] for row in datasource_rows} == {
        "agent-service-client", "rag-service-client",
    }
    assert all(
        row["path"].removeprefix("^/internal/").removeprefix("^/")
        .startswith(row["audience"].removesuffix("-client") + "/")
        for row in datasource_rows
    )


def test_every_gateway_route_uses_its_url_service_client():
    for row in module.inventory(ROOT):
        service = row["path"].removeprefix("^/internal/").removeprefix("^/").split("/", 1)[0]
        assert row["audience"] == service + "-client", row["path"]


def test_memory_index_routes_use_rag_service_client():
    rows = module.inventory(ROOT)
    memory_rows = [
        row for row in rows
        if any(permission.startswith("memory#") for permission in row["permissions"])
    ]
    assert {row["audience"] for row in memory_rows} == {
        "user-service-client", "rag-service-client",
    }
    assert {
        permission for row in memory_rows for permission in row["permissions"]
    } == {
        "memory#create", "memory#delete", "memory#read", "memory#update",
        "memory#search", "memory#write",
    }
    assert any(row["path"].startswith("^/internal/rag-service/") for row in memory_rows)

def test_keycloak_bootstrap_mounts_every_router_the_inventory_scans():
    """The bootstrap container builds the inventory from mounted routers.

    A router glob outside its mounts yields no rows, and the reconcile then
    strips that service's Keycloak permissions on every startup (all its
    gateway routes return 403, even for system-admin).
    """
    compose = (ROOT / "deploy/docker/docker-compose-services.yml").read_text(
        encoding="utf-8"
    )
    # The service block runs until the next two-space-indented service key.
    after = compose.split("\n  keycloak-bootstrap:\n", 1)[1]
    block = re.split(r"\n  [A-Za-z0-9_.-]+:\n", after, maxsplit=1)[0]
    mounts = [
        Path(match.group(1))
        for match in re.finditer(r"- [^:\n]+:(/workspace/[^:\n]+):ro", block)
    ]
    workspace = Path("/workspace")
    for service, pattern in module.ROUTE_GLOBS.items():
        scanned = workspace / "apps" / service / pattern.split("*", 1)[0]
        assert any(
            scanned == mount or mount in scanned.parents for mount in mounts
        ), f"{service} routers ({pattern}) are not mounted into keycloak-bootstrap"
        assert list((ROOT / "apps" / service).glob(pattern)), (
            f"{service} route glob {pattern} matches no router"
        )


def test_shared_projection_loads_without_the_web_stack(monkeypatch):
    # The bootstrap container runs this file on plain Python: no FastAPI, no
    # pydantic, so no ``error_contract``. Importing it must not need them.
    import sys

    monkeypatch.setitem(sys.modules, "error_contract", None)
    path = ROOT / "apps/user-service/src/repository/keycloak_authorization.py"
    spec = importlib.util.spec_from_file_location("standalone_authorization", path)
    standalone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(standalone)

    assert callable(standalone.reconcile)
    assert issubclass(standalone.DependencyUnavailableError, Exception)


def test_cached_mcp_tools_need_read_while_live_discovery_needs_sync():
    # Reading the tools a server last synced is a database read; only live
    # discovery contacts the server and changes its status.
    rows = module.inventory(ROOT)

    def permissions(path):
        return next(
            r["permissions"]
            for r in rows
            if "GET" in r["methods"] and re.fullmatch(r["path"], path)
        )

    base = "/agent-service/api/v1/admin/mcp"
    assert permissions(f"{base}/servers/1001/tools") == ["mcp_tool#read"]
    assert permissions(f"{base}/server/1001/tools/snapshots") == ["mcp_provider#sync"]
