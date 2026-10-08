from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.keycloak_role_cutover import reconcile_role_metadata
from src.service.permission_sync_service import PermissionSyncService


@pytest.mark.asyncio
async def test_sync_reports_permissions_from_scopes_and_roles_without_writing_catalog():
    repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(name="agent:read", service="agent-service"),
                SimpleNamespace(name="document:read", service="rag-service"),
            ]
        )
    )
    result = await PermissionSyncService(repo).sync_permissions()
    assert result == {
        "synced_count": 2,
        "sources": [
            {
                "service": "agent-service",
                "path": "Keycloak feature scopes and client role attributes",
                "loaded": True,
                "count": 1,
                "error": None,
            },
            {
                "service": "rag-service",
                "path": "Keycloak feature scopes and client role attributes",
                "loaded": True,
                "count": 1,
                "error": None,
            },
        ],
    }


@pytest.mark.asyncio
async def test_legacy_metadata_reconciliation_does_not_recreate_catalog_role():
    keycloak = SimpleNamespace(request=AsyncMock(return_value=None))
    changed = await reconcile_role_metadata(
        keycloak,
        {"permissions": [{"name": "agent:read", "service": "agent-service"}]},
        apply=True,
    )
    assert changed == 0
    keycloak.request.assert_not_called()
