from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.permission_service import PermissionService


@pytest.mark.asyncio
async def test_permission_coverage_groups_catalog_by_feature_entity_and_action():
    service = PermissionService()
    service.repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="user:list",
                    feature="access",
                    entity="user",
                    action="list",
                    service="user-service",
                    is_system=False,
                ),
                SimpleNamespace(
                    name="system.settings:update",
                    feature="system",
                    entity="system.settings",
                    action="update",
                    service="user-service",
                    is_system=True,
                ),
            ]
        )
    )

    coverage = await service.get_coverage()

    assert coverage["features"]["access"]["entities"]["user"]["actions"]["list"] == {
        "permission": "user:list",
        "service": "user-service",
        "is_system": False,
    }
    assert (
        coverage["features"]["system"]["entities"]["system.settings"]["actions"]["update"][
            "permission"
        ]
        == "system.settings:update"
    )


@pytest.mark.asyncio
async def test_permission_catalog_exposes_configured_service_client(monkeypatch):
    monkeypatch.setattr(
        "src.service.permission_service.env",
        SimpleNamespace(
            KEYCLOAK_AGENT_SERVICE_CLIENT_ID="custom-agent-client",
            KEYCLOAK_RAG_SERVICE_CLIENT_ID="custom-rag-client",
            KEYCLOAK_TOOLS_SERVICE_CLIENT_ID="custom-tools-client",
            KEYCLOAK_USER_SERVICE_CLIENT_ID="custom-user-client",
        ),
    )
    service = PermissionService()
    service.repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="agent:read",
                    label="Read agents",
                    description=None,
                    entity="agent",
                    service="agent-service",
                    action="read",
                    feature="agents",
                    is_system=False,
                ),
                SimpleNamespace(
                    name="custom:view",
                    label="View custom",
                    description=None,
                    entity="custom",
                    service="unknown-service",
                    action="view",
                    feature=None,
                    is_system=False,
                ),
            ]
        )
    )

    permissions = await service.list_permissions()

    assert permissions[0]["service_client"] == "custom-agent-client"
    assert permissions[1]["service_client"] is None
