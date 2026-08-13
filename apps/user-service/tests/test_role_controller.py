from unittest.mock import AsyncMock

import pytest

from src.controller.role_controller import CompositeRoleController


@pytest.mark.asyncio
async def test_list_roles_exposes_roles_alias_for_admin_users():
    roles = [{"name": "system-admin", "description": "System administrator"}]
    controller = CompositeRoleController()
    controller.service = AsyncMock()
    controller.service.list_roles.return_value = roles

    response = await controller.list_roles()

    assert response["composite_roles"] == roles
    assert response["roles"] == roles
