"""Focused tests for resource-permission serialization."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.repository.resource_permission_repository import ResourcePermissionRepository


class _UnloadedPermission:
    id = uuid.uuid4()
    resource_type = "agent"
    resource_id = "agent-1"
    resource_name = "Agent"
    organization_id = uuid.uuid4()
    user_id = None
    permission_level = "read"
    is_inherited = False
    granted_by = uuid.uuid4()
    granted_at = datetime.now(UTC)
    expires_at = None

    @property
    def organization(self):
        raise AssertionError("serialization attempted to load organization")

    @property
    def user(self):
        raise AssertionError("serialization attempted to load user")


def test_to_dict_never_touches_relationships() -> None:
    """Serialization never triggers relationship I/O; identities resolve through Keycloak."""
    result = ResourcePermissionRepository()._to_dict(
        _UnloadedPermission(),  # type: ignore[arg-type]
    )

    assert result["resource_id"] == "agent-1"
    assert result["organization"] is None
    assert result["user"] is None


@pytest.mark.asyncio
async def test_identity_details_are_resolved_from_keycloak_repositories(monkeypatch):
    from src.repository.organization_repository import OrganizationRepository

    organization = {"id": _UnloadedPermission.organization_id, "name": "Research", "code": "R"}
    lookup = AsyncMock(return_value=organization)
    monkeypatch.setattr(OrganizationRepository, "get_by_id", lookup)
    repo = ResourcePermissionRepository()
    payload = repo._to_dict(_UnloadedPermission())
    result = await repo._with_identity(payload)
    assert result["organization"]["name"] == "Research"
    lookup.assert_awaited_once_with(_UnloadedPermission.organization_id)
