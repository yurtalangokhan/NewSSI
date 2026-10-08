"""Cross-service identity and effective-level contracts."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from error_contract import ForbiddenError
import pytest

from src.controller.resource_permission_controller import ResourcePermissionController
from src.service.resource_permission_service import ResourcePermissionService


@pytest.mark.asyncio
async def test_check_resolves_the_keycloak_subject_by_its_id():
    controller = ResourcePermissionController()
    local_id = uuid.uuid4()
    subject = str(local_id)
    controller.identity_service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=local_id)),
    )
    controller.service = SimpleNamespace(
        check_resource_access=AsyncMock(return_value={"allowed": True})
    )
    await controller.check_permission(subject, "agent", "42", "execute")
    assert controller.service.check_resource_access.await_args.kwargs["user_id"] == local_id


@pytest.mark.asyncio
async def test_accessible_resources_filter_by_required_level():
    controller = ResourcePermissionController()
    local_id = uuid.uuid4()
    controller.identity_service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(id=local_id)),
    )
    controller.service = SimpleNamespace(
        get_user_accessible_resources=AsyncMock(
            return_value=[
                {"resource_id": "readable", "permission_level": "read"},
                {"resource_id": "execute-only", "permission_level": "execute"},
            ]
        )
    )
    result = await controller.get_user_accessible_resources(local_id, "rag_collection", "read")
    assert [item["resource_id"] for item in result["resources"]] == ["readable"]


@pytest.mark.asyncio
async def test_resource_wide_listing_is_not_granted_by_broad_action_permission():
    controller = ResourcePermissionController()
    controller.service = ResourcePermissionService()
    controller.service.permission_resolver = SimpleNamespace(
        resolve_effective_access=AsyncMock(return_value=(["permission:read"], False))
    )
    controller.service.perm_repo = SimpleNamespace(
        get_resource_permissions=AsyncMock(return_value=[])
    )
    with pytest.raises(ForbiddenError) as denied:
        await controller.get_resource_permissions("agent", "1", actor_id=uuid.uuid4())
    assert denied.value.status_code == 403
    controller.service.perm_repo.get_resource_permissions.assert_not_awaited()
