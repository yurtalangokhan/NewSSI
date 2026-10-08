"""Enterprise admin inherits every managed permission except System Settings."""

import re
from pathlib import Path

import pytest


class FakeKeycloak:
    def __init__(self):
        self.roles = {
            "enterprise-admin": self.role("realm", "enterprise-admin", [], composite=True),
            "agent-workspace-manager": self.role("agent-manager", "agent-workspace-manager", ["agent:read"]),
            "agent-workspace-admin": self.role("agent-admin", "agent-workspace-admin", ["agent:read", "agent:delete"]),
            "knowledge-admin": self.role("rag-admin", "knowledge-admin", ["graph:build"]),
            "access-admin": self.role("access-admin", "access-admin", ["user:manage"]),
            "tooling-admin": self.role("tools-admin", "tooling-admin", ["tool:manage"]),
        }
        self.by_id = {role["id"]: role for role in self.roles.values()}
        self.clients = {
            "agent-service-client": ["agent-workspace-manager", "agent-workspace-admin"],
            "rag-service-client": ["knowledge-admin"],
            "tools-service-client": ["tooling-admin"],
            "user-service-client": ["access-admin"],
        }
        self.children = [self.roles["agent-workspace-manager"], self.roles["tooling-admin"]]
        self.scopes = {
            "agent-service-client": {
                "agent": ["delete"], "schedule": ["read"], "tool": ["manage"],
            },
            "rag-service-client": {"graph": ["build"], "memory": ["search"]},
            "tools-service-client": {"tool": ["manage"]},
            "user-service-client": {"user": ["manage"], "system.settings": ["read"]},
        }
        self.writes = []

    @staticmethod
    def role(role_id, name, permissions, *, composite=False):
        return {
            "id": role_id,
            "name": name,
            "composite": composite,
            "attributes": {"agentic.permissions": list(permissions), "agentic.builtin": ["true"]},
        }

    async def client_id(self, name):
        assert name in self.clients
        return name

    async def pages(self, path):
        name = path.removeprefix("/clients/").removesuffix("/roles")
        return [self.roles[role] for role in self.clients[name]]

    async def request(self, method, path, **kwargs):
        if method == "GET" and path.endswith("/authz/resource-server/resource"):
            name = path.removeprefix("/clients/").removesuffix("/authz/resource-server/resource")
            return [
                {"name": entity, "type": "agentic:feature", "scopes": [{"name": scope} for scope in scopes]}
                for entity, scopes in self.scopes[name].items()
            ]
        if method == "GET" and path == "/roles/enterprise-admin":
            return self.roles["enterprise-admin"]
        if method == "GET" and path == "/roles-by-id/realm/composites":
            return self.children
        if path.startswith("/roles-by-id/"):
            role_id = path.removeprefix("/roles-by-id/")
            if method == "GET":
                return self.by_id[role_id]
            if method == "PUT":
                self.writes.append((method, path))
                self.by_id[role_id].update(kwargs["json"])
                return None
            if method == "POST" and role_id == "realm/composites":
                self.writes.append((method, path))
                self.children.extend(self.by_id[role["id"]] for role in kwargs["json"])
                return None
        raise AssertionError(f"Unexpected request: {method} {path}")


CLIENT_NAMES = (
    "agent-service-client", "rag-service-client", "tools-service-client", "user-service-client",
)


@pytest.mark.asyncio
async def test_dry_run_and_apply_cover_all_managed_grants_without_system_settings():
    from scripts.reconcile_enterprise_admin import reconcile_enterprise_admin

    client = FakeKeycloak()
    plan = await reconcile_enterprise_admin(client, apply=False, client_names=CLIENT_NAMES)
    assert set(plan["role_additions"]) == {
        "agent-workspace-admin", "knowledge-admin", "access-admin",
    }
    assert set(plan["view_additions"]) == {
        "mail_config:view", "mcp_tool:view", "provider:view", "web_search:view",
    }
    assert plan["scope_additions"] == {
        "agent-service-client": ["schedule:read", "tool:manage"],
        "rag-service-client": ["memory:search"],
    }
    assert client.writes == []

    await reconcile_enterprise_admin(client, apply=True, client_names=CLIENT_NAMES)
    assert len(client.writes) == 3
    assert await reconcile_enterprise_admin(client, apply=True, client_names=CLIENT_NAMES) == {
        "role_additions": [], "view_additions": [], "scope_additions": {},
    }
    assert len(client.writes) == 3
    assert "system.settings:view" not in client.roles["agent-workspace-admin"]["attributes"]["agentic.permissions"]


@pytest.mark.asyncio
async def test_refuses_admin_bundle_that_grants_system_settings():
    from scripts.reconcile_enterprise_admin import reconcile_enterprise_admin

    client = FakeKeycloak()
    client.roles["access-admin"]["attributes"]["agentic.permissions"].append("system.settings:view")
    with pytest.raises(ValueError, match="System Settings"):
        await reconcile_enterprise_admin(client, apply=True, client_names=CLIENT_NAMES)
    assert client.writes == []


@pytest.mark.asyncio
async def test_refuses_an_uncovered_managed_permission():
    from scripts.reconcile_enterprise_admin import reconcile_enterprise_admin

    client = FakeKeycloak()
    client.roles["agent-workspace-manager"]["attributes"]["agentic.permissions"].append(
        "future:manage"
    )
    client.children = [client.roles["tooling-admin"]]
    with pytest.raises(ValueError, match="future:manage"):
        await reconcile_enterprise_admin(client, apply=True, client_names=CLIENT_NAMES)
    assert client.writes == []


def test_ui_view_grants_match_enabled_admin_route_registry():
    from scripts.reconcile_enterprise_admin import MISSING_PAGE_VIEWS

    routes = Path(__file__).resolve().parents[2] / "web/src/lib/navigation/admin-routes.ts"
    source = routes.read_text(encoding="utf-8")
    page_views = set(re.findall(r'requiredPermissions: \["([^"]+:view)"\]', source))
    assert set(MISSING_PAGE_VIEWS) <= page_views
