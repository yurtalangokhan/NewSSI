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
