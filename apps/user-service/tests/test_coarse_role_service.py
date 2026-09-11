from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.coarse_role_service import RoleService


@pytest.mark.asyncio
async def test_aggregated_permissions_reads_normalized_role_permissions():
    service = RoleService()
    service.repo = SimpleNamespace(
        get_permissions_by_names=AsyncMock(
            return_value={
                "agent-workspace-user": ["agent:list", "project:read"],
                "tooling-user": ["tool:read"],
            }
        )
    )

    permissions = await service.get_aggregated_permissions(["agent-workspace-user", "tooling-user"])

    assert permissions == ["agent:list", "project:read", "tool:read"]
    service.repo.get_permissions_by_names.assert_awaited_once_with(
        ["agent-workspace-user", "tooling-user"]
    )
