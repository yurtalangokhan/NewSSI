"""The v1 Keycloak projection follows the gateway's route contract."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.provision_v1_authorization import (
    check_existing,
    project_gateway,
    projection_settings,
    route_uris,
    sync_existing_scope_permissions,
    verify_scope_policy_links,
)


def test_route_uris_supports_parameters_optional_slash_and_trailing_wildcard():
    assert route_uris("^/rag-service/api/v1/collections/[^/]+/?$") == [
        "/rag-service/api/v1/collections/{p0}",
        "/rag-service/api/v1/collections/{p0}/",
    ]
    assert route_uris("^/agent-service/api/v1/admin/ollama/models/.+/?$") == [
        "/agent-service/api/v1/admin/ollama/models/*"
    ]


def test_route_uris_rejects_unrecognized_regex():
    with pytest.raises(ValueError, match="unsupported"):
        route_uris("^/service/(foo|bar)/?$")


def test_project_gateway_groups_uris_by_client_and_permission_resource():
    rows = [
        {
            "audience": "rag-service-client",
            "path": "^/rag-service/items/?$",
            "permissions": ["document#read", "document#update"],
        },
        {
            "audience": "rag-service-client",
            "path": "^/rag-service/items/[^/]+/?$",
            "permissions": ["document#read"],
        },
        {
            "audience": "tools-service-client",
            "path": "^/tools-service/mcp/?$",
            "permissions": [],
            "authenticated_only": True,
        },
    ]
    result = project_gateway(rows)
    assert result["rag-service-client"]["document"]["scopes"] == ["read", "update"]
    assert result["rag-service-client"]["document"]["uris"] == [
        "/rag-service/items",
        "/rag-service/items/",
        "/rag-service/items/{p0}",
        "/rag-service/items/{p0}/",
    ]
    assert result["tools-service-client"]["agentic:authenticated"]["scopes"] == []
    assert result["tools-service-client"]["agentic:authenticated"]["uris"] == [
        "/tools-service/mcp",
        "/tools-service/mcp/",
    ]


def test_project_gateway_accepts_configured_client_id():
    result = project_gateway(
        [{"audience": "custom-rag", "path": "^/rag-service/items$",
          "permissions": ["document#read"]}],
        service_clients={"rag-service": "custom-rag"},
    )
    assert result["custom-rag"]["document"]["uris"] == ["/rag-service/items"]


def test_project_gateway_rejects_unprotected_or_mismatched_routes():
    with pytest.raises(ValueError, match="neither"):
        project_gateway(
            [{"audience": "rag-service", "path": "^/rag-service/open$", "permissions": []}]
        )
    with pytest.raises(ValueError, match="audience"):
        project_gateway(
            [
                {
                    "audience": "rag-service",
                    "path": "^/user-service/items$",
                    "permissions": ["document#read"],
                }
            ]
        )


def test_checked_in_gateway_inventory_projects_under_route_service_clients():
    root = Path(__file__).resolve().parents[3]
    rows = json.loads((root / "configs/apisix/gateway-policies.json").read_text())
    projected = project_gateway(rows)
    assert projected["user-service-client"]["memory"]["scopes"] == [
        "create", "delete", "read", "update",
    ]
    assert projected["rag-service-client"]["memory"]["scopes"] == ["search", "write"]
    assert projected["agent-service-client"]["datasource"]["scopes"] == [
        "create", "delete", "read", "sync", "update",
    ]
    assert projected["rag-service-client"]["datasource"]["scopes"] == ["read", "sync"]


def test_projection_settings_keeps_uri_resources_and_denies_ungranted_scopes():
    resources = {
        "document": {"uris": ["/rag-service/items"], "scopes": ["read", "delete"]},
        "agentic:authenticated": {"uris": ["/rag-service/health"], "scopes": []},
    }
    roles = [
        {
            "id": "role-1",
            "name": "reader",
            "clientRole": True,
            "attributes": {"agentic.permissions": ["document:read"]},
        }
    ]
    settings = projection_settings(resources, roles)
    assert {r["name"]: r["uris"] for r in settings["resources"]} == {
        "document": ["/rag-service/items"],
        "agentic:authenticated": ["/rag-service/health"],
    }
    names = {policy["name"] for policy in settings["policies"]}
    assert "agentic:permission:document#read" in names
    assert "agentic:permission:document#delete" not in names


def test_check_existing_rejects_unmanaged_objects_and_accepts_defaults_or_own_projection():
    defaults = (
        [{"name": "Default Resource"}],
        [{"name": "Default Permission"}, {"name": "Default Policy"}],
    )
    assert check_existing(*defaults)
    assert check_existing(
        [{"name": "document", "type": "agentic:feature"}], [{"name": "agentic:role:role-1"}]
    )
    with pytest.raises(ValueError, match="unmanaged"):
        check_existing([{"name": "custom"}], [])


@pytest.mark.asyncio
async def test_existing_scope_policy_is_updated_with_new_role_associations():
    base = "/clients/user-id/authz/resource-server"
    previous = [{"id": "permission-id", "name": "agentic:permission:memory#read", "type": "scope"}]
    desired = [{
        "name": "agentic:permission:memory#read",
        "type": "scope",
        "logic": "POSITIVE",
        "config": {
            "resources": '["memory"]',
            "scopes": '["read"]',
            "applyPolicies": '["agentic:role:admin", "agentic:role:self-service"]',
        },
    }]
    admin = AsyncMock()

    await sync_existing_scope_permissions(admin, base, previous, desired)

    admin.request.assert_awaited_once_with(
        "PUT",
        base + "/permission/scope/permission-id",
        json={
            "id": "permission-id",
            "name": "agentic:permission:memory#read",
            "type": "scope",
            "logic": "POSITIVE",
            "resources": ["memory"],
            "scopes": ["read"],
            "policies": ["agentic:role:admin", "agentic:role:self-service"],
        },
    )


@pytest.mark.asyncio
async def test_verification_rejects_stale_scope_policy_associations():
    base = "/clients/user-id/authz/resource-server"
    current = [{"id": "permission-id", "name": "agentic:permission:memory#read"}]
    desired = [{
        "name": "agentic:permission:memory#read",
        "type": "scope",
        "config": {"applyPolicies": '["agentic:role:admin", "agentic:role:self-service"]'},
    }]
    admin = AsyncMock()
    admin.request.return_value = [{"name": "agentic:role:admin"}]

    with pytest.raises(RuntimeError, match="policy associations"):
        await verify_scope_policy_links(admin, base, current, desired)

    admin.request.return_value = [
        {"name": "agentic:role:admin"}, {"name": "agentic:role:self-service"},
    ]
    await verify_scope_policy_links(admin, base, current, desired)
